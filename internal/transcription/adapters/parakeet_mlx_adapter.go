package adapters

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"scriberr/internal/transcription/interfaces"
	"scriberr/pkg/logger"
)

// ParakeetMLXAdapter implements the TranscriptionAdapter interface for Parakeet MLX (Apple Silicon)
type ParakeetMLXAdapter struct {
	*BaseAdapter
	envPath string
}

// NewParakeetMLXAdapter creates a new Parakeet MLX adapter
func NewParakeetMLXAdapter(envPath string) *ParakeetMLXAdapter {
	capabilities := interfaces.ModelCapabilities{
		ModelID:     "parakeet_mlx",
		ModelFamily: "parakeet_mlx",
		DisplayName: "Parakeet MLX (Apple Silicon)",
		Description: "Ultra-fast transcription using MLX on Apple Silicon. ~50x realtime.",
		Version:     "0.6.3",
		SupportedLanguages: []string{
			"auto",
			"be", "bg", "cs", "da", "de", "el", "en", "es", "fi", "fr",
			"he", "hi", "hr", "hu", "it", "ja", "ko", "nl", "no", "pl",
			"pt", "ro", "ru", "sk", "sl", "sv", "uk", "zh",
		},
		SupportedFormats:  []string{"wav", "flac", "mp3", "ogg", "m4a"},
		RequiresGPU:       false, // Uses Apple Silicon Neural Engine / GPU via MLX
		MemoryRequirement: 2048,  // 2GB — MLX is very memory efficient
		Features: map[string]bool{
			"timestamps":    true,
			"word_level":    true,
			"long_form":     true,
			"high_quality":  true,
			"apple_silicon": true,
		},
		Metadata: map[string]string{
			"engine":      "parakeet_mlx",
			"framework":   "mlx",
			"license":     "CC-BY-4.0",
			"language":    "multilingual",
			"sample_rate": "16000",
			"format":      "16khz_mono_wav",
		},
	}

	schema := []interfaces.ParameterSchema{
		{
			Name:        "timestamps",
			Type:        "bool",
			Required:    false,
			Default:     true,
			Description: "Include word and segment level timestamps",
			Group:       "basic",
		},
		{
			Name:        "output_format",
			Type:        "string",
			Required:    false,
			Default:     "json",
			Options:     []string{"json", "text"},
			Description: "Output format for results",
			Group:       "basic",
		},
		{
			Name:        "auto_convert_audio",
			Type:        "bool",
			Required:    false,
			Default:     true,
			Description: "Automatically convert audio to 16kHz mono WAV",
			Group:       "advanced",
		},
	}

	baseAdapter := NewBaseAdapter("parakeet_mlx", envPath, capabilities, schema)

	adapter := &ParakeetMLXAdapter{
		BaseAdapter: baseAdapter,
		envPath:     envPath,
	}

	return adapter
}

// GetSupportedModels returns the specific Parakeet MLX model available
func (p *ParakeetMLXAdapter) GetSupportedModels() []string {
	return []string{"mlx-community/parakeet-tdt-0.6b-v3"}
}

// getASREnvPython returns the path to the asr-env Python interpreter.
// Parakeet MLX uses the system asr-env venv, not Scriberr's internal uv venv.
func (p *ParakeetMLXAdapter) getASREnvPython() string {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		logger.Warn("Failed to get home directory, falling back to ~/asr-env", "error", err)
		return filepath.Join(os.Getenv("HOME"), "asr-env", "bin", "python")
	}
	return filepath.Join(homeDir, "asr-env", "bin", "python")
}

// PrepareEnvironment sets up the Parakeet MLX environment.
// Unlike the NeMo adapter, parakeet-mlx downloads its model automatically on first use,
// and it uses the system asr-env venv rather than Scriberr's internal uv-managed venv.
func (p *ParakeetMLXAdapter) PrepareEnvironment(ctx context.Context) error {
	logger.Info("Preparing Parakeet MLX environment", "env_path", p.envPath)

	// Ensure env directory exists for script deployment
	if err := os.MkdirAll(p.envPath, 0755); err != nil {
		return fmt.Errorf("failed to create parakeet_mlx directory: %w", err)
	}

	// Copy the transcription script from embedded files
	if err := p.copyTranscriptionScript(); err != nil {
		return fmt.Errorf("failed to copy transcription script: %w", err)
	}

	// Verify that the asr-env Python exists and has parakeet_mlx installed
	pythonPath := p.getASREnvPython()
	if _, err := os.Stat(pythonPath); os.IsNotExist(err) {
		return fmt.Errorf("asr-env Python not found at %s — parakeet-mlx requires ~/asr-env with parakeet_mlx installed", pythonPath)
	}

	// Quick check that parakeet_mlx is importable
	cmd := exec.CommandContext(ctx, pythonPath, "-c", "import parakeet_mlx; print('ok')")
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("parakeet_mlx not available in %s: %w\n%s", pythonPath, err, strings.TrimSpace(string(out)))
	}

	p.initialized = true
	logger.Info("Parakeet MLX environment ready", "python", pythonPath)
	return nil
}

// copyTranscriptionScript deploys the embedded Python script to the env directory
func (p *ParakeetMLXAdapter) copyTranscriptionScript() error {
	if err := os.MkdirAll(p.envPath, 0755); err != nil {
		return fmt.Errorf("failed to create directory: %w", err)
	}

	scriptContent, err := nvidiaScripts.ReadFile("py/nvidia/parakeet_mlx_transcribe.py")
	if err != nil {
		return fmt.Errorf("failed to read embedded parakeet_mlx_transcribe.py: %w", err)
	}

	scriptPath := filepath.Join(p.envPath, "parakeet_mlx_transcribe.py")
	if err := os.WriteFile(scriptPath, scriptContent, 0755); err != nil {
		return fmt.Errorf("failed to write transcription script: %w", err)
	}

	return nil
}

// Transcribe processes audio using Parakeet MLX
func (p *ParakeetMLXAdapter) Transcribe(ctx context.Context, input interfaces.AudioInput, params map[string]interface{}, procCtx interfaces.ProcessingContext) (*interfaces.TranscriptResult, error) {
	startTime := time.Now()
	p.LogProcessingStart(input, procCtx)
	defer func() {
		p.LogProcessingEnd(procCtx, time.Since(startTime), nil)
	}()

	// Validate input
	if err := p.ValidateAudioInput(input); err != nil {
		return nil, fmt.Errorf("invalid audio input: %w", err)
	}

	// Validate parameters
	if err := p.ValidateParameters(params); err != nil {
		return nil, fmt.Errorf("invalid parameters: %w", err)
	}

	// Create temporary directory
	tempDir, err := p.CreateTempDirectory(procCtx)
	if err != nil {
		return nil, fmt.Errorf("failed to create temp directory: %w", err)
	}
	defer p.CleanupTempDirectory(tempDir)

	// Convert audio if needed (16kHz mono WAV)
	audioInput := input
	if p.GetBoolParameter(params, "auto_convert_audio") {
		convertedInput, err := p.ConvertAudioFormat(ctx, input, "wav", 16000)
		if err != nil {
			logger.Warn("Audio conversion failed, using original", "error", err)
		} else {
			audioInput = convertedInput
		}
	}

	// Build command
	outputFile := filepath.Join(tempDir, "result.json")
	scriptPath := filepath.Join(p.envPath, "parakeet_mlx_transcribe.py")
	pythonPath := p.getASREnvPython()

	args := []string{
		scriptPath,
		audioInput.FilePath,
		"--output", outputFile,
	}

	cmd := exec.CommandContext(ctx, pythonPath, args...)
	cmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

	// Setup log file
	logFile, err := os.OpenFile(filepath.Join(procCtx.OutputDirectory, "transcription.log"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		logger.Warn("Failed to create log file", "error", err)
	} else {
		defer logFile.Close()
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}

	logger.Info("Executing Parakeet MLX command", "python", pythonPath, "script", scriptPath, "audio", audioInput.FilePath)

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.Canceled {
			return nil, fmt.Errorf("transcription was cancelled")
		}

		logPath := filepath.Join(procCtx.OutputDirectory, "transcription.log")
		logTail, readErr := p.ReadLogTail(logPath, 2048)
		if readErr != nil {
			logger.Warn("Failed to read log tail", "error", readErr)
		}

		logger.Error("Parakeet MLX execution failed", "error", err)
		return nil, fmt.Errorf("Parakeet MLX execution failed: %w\nLogs:\n%s", err, logTail)
	}

	// Parse result
	result, err := p.parseResult(tempDir)
	if err != nil {
		return nil, fmt.Errorf("failed to parse result: %w", err)
	}

	result.ProcessingTime = time.Since(startTime)
	result.ModelUsed = "parakeet-mlx-tdt-0.6b-v3"
	result.Metadata = p.CreateDefaultMetadata(params)

	logger.Info("Parakeet MLX transcription completed",
		"segments", len(result.Segments),
		"words", len(result.WordSegments),
		"processing_time", result.ProcessingTime)

	return result, nil
}

// parseResult parses the Parakeet MLX output JSON
func (p *ParakeetMLXAdapter) parseResult(tempDir string) (*interfaces.TranscriptResult, error) {
	resultFile := filepath.Join(tempDir, "result.json")

	data, err := os.ReadFile(resultFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read result file: %w", err)
	}

	var mlxResult struct {
		Transcription     string  `json:"transcription"`
		SourceLanguage    string  `json:"source_language"`
		TargetLanguage    string  `json:"target_language"`
		Task              string  `json:"task"`
		ProcessingTime    float64 `json:"processing_time"`
		AudioFile         string  `json:"audio_file"`
		WordTimestamps    []struct {
			Word  string  `json:"word"`
			Start float64 `json:"start"`
			End   float64 `json:"end"`
		} `json:"word_timestamps"`
		SegmentTimestamps []struct {
			Text  string  `json:"text"`
			Start float64 `json:"start"`
			End   float64 `json:"end"`
		} `json:"segment_timestamps"`
	}

	if err := json.Unmarshal(data, &mlxResult); err != nil {
		return nil, fmt.Errorf("failed to parse JSON result: %w", err)
	}

	result := &interfaces.TranscriptResult{
		Text:         mlxResult.Transcription,
		Language:     "auto",
		Segments:     make([]interfaces.TranscriptSegment, len(mlxResult.SegmentTimestamps)),
		WordSegments: make([]interfaces.TranscriptWord, len(mlxResult.WordTimestamps)),
		Confidence:   0.0,
	}

	for i, seg := range mlxResult.SegmentTimestamps {
		result.Segments[i] = interfaces.TranscriptSegment{
			Start: seg.Start,
			End:   seg.End,
			Text:  seg.Text,
		}
	}

	for i, word := range mlxResult.WordTimestamps {
		result.WordSegments[i] = interfaces.TranscriptWord{
			Start: word.Start,
			End:   word.End,
			Word:  word.Word,
			Score: 1.0, // Parakeet MLX doesn't provide word-level confidence
		}
	}

	return result, nil
}

// GetEstimatedProcessingTime provides Parakeet MLX-specific time estimation
func (p *ParakeetMLXAdapter) GetEstimatedProcessingTime(input interfaces.AudioInput) time.Duration {
	// Parakeet MLX processes at ~50x realtime on Apple Silicon
	if input.Duration > 0 {
		return time.Duration(float64(input.Duration) / 50.0)
	}
	// Fallback: base estimate scaled down significantly
	baseTime := p.BaseAdapter.GetEstimatedProcessingTime(input)
	return time.Duration(float64(baseTime) * 0.1)
}
