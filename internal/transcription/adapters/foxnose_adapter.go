package adapters

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"scriberr/internal/transcription/interfaces"
	"scriberr/pkg/logger"
)

//go:embed py/foxnose/*
var foxnoseScripts embed.FS

// FoxNoseAdapter implements the DiarizationAdapter interface using FoxNoseTech/diarize.
// ~8x faster than pyannote, no HuggingFace token required.
type FoxNoseAdapter struct {
	*BaseAdapter
	envPath string
}

// NewFoxNoseAdapter creates a new FoxNose diarization adapter.
func NewFoxNoseAdapter(envPath string) *FoxNoseAdapter {
	capabilities := interfaces.ModelCapabilities{
		ModelID:            "foxnose",
		ModelFamily:        "foxnose",
		DisplayName:        "FoxNose Fast Diarization",
		Description:        "FoxNoseTech/diarize — fast speaker diarization, no API keys required",
		Version:            "1.0.0",
		SupportedLanguages: []string{"*"},
		SupportedFormats:   []string{"wav", "mp3", "flac", "m4a", "ogg"},
		RequiresGPU:        false,
		MemoryRequirement:  1024,
		Features: map[string]bool{
			"speaker_detection":   true,
			"speaker_constraints": true,
			"confidence_scores":   false,
			"flexible_speakers":   true,
		},
		Metadata: map[string]string{
			"engine":  "foxnosetech_diarize",
			"license": "Apache-2.0",
		},
	}

	schema := []interfaces.ParameterSchema{
		{
			Name:        "min_speakers",
			Type:        "int",
			Required:    false,
			Default:     nil,
			Min:         &[]float64{1}[0],
			Max:         &[]float64{20}[0],
			Description: "Minimum number of speakers",
			Group:       "basic",
		},
		{
			Name:        "max_speakers",
			Type:        "int",
			Required:    false,
			Default:     nil,
			Min:         &[]float64{1}[0],
			Max:         &[]float64{20}[0],
			Description: "Maximum number of speakers",
			Group:       "basic",
		},
		{
			Name:    "output_format",
			Type:    "string",
			Default: OutputFormatJSON,
			Group:   "advanced",
		},
	}

	baseAdapter := NewBaseAdapter("foxnose", envPath, capabilities, schema)

	return &FoxNoseAdapter{
		BaseAdapter: baseAdapter,
		envPath:     envPath,
	}
}

func (f *FoxNoseAdapter) GetMaxSpeakers() int { return 20 }
func (f *FoxNoseAdapter) GetMinSpeakers() int { return 1 }

func (f *FoxNoseAdapter) getASREnvPython() string {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join(os.Getenv("HOME"), "asr-env", "bin", "python")
	}
	return filepath.Join(homeDir, "asr-env", "bin", "python")
}

// PrepareEnvironment ensures the diarize script exists and the package is installed.
func (f *FoxNoseAdapter) PrepareEnvironment(ctx context.Context) error {
	logger.Info("Preparing FoxNose diarization environment")

	// Copy the diarization script
	if err := f.copyScript(); err != nil {
		return fmt.Errorf("failed to create diarization script: %w", err)
	}

	// Verify diarize is importable
	pythonPath := f.getASREnvPython()
	testCmd := exec.CommandContext(ctx, pythonPath, "-c", "from diarize import diarize; print('ok')")
	if out, err := testCmd.CombinedOutput(); err != nil {
		return fmt.Errorf("diarize package not available in %s: %w\n%s", pythonPath, err, string(out))
	}

	f.initialized = true
	logger.Info("FoxNose diarization environment ready")
	return nil
}

func (f *FoxNoseAdapter) copyScript() error {
	scriptDir := filepath.Join(f.envPath, "foxnose")
	if err := os.MkdirAll(scriptDir, 0755); err != nil {
		return err
	}

	content, err := foxnoseScripts.ReadFile("py/foxnose/foxnose_diarize.py")
	if err != nil {
		return fmt.Errorf("failed to read embedded script: %w", err)
	}

	return os.WriteFile(filepath.Join(scriptDir, "foxnose_diarize.py"), content, 0755)
}

// Diarize processes audio using FoxNoseTech/diarize.
func (f *FoxNoseAdapter) Diarize(ctx context.Context, input interfaces.AudioInput, params map[string]interface{}, procCtx interfaces.ProcessingContext) (*interfaces.DiarizationResult, error) {
	startTime := time.Now()
	f.LogProcessingStart(input, procCtx)
	defer func() {
		f.LogProcessingEnd(procCtx, time.Since(startTime), nil)
	}()

	if err := f.ValidateAudioInput(input); err != nil {
		return nil, fmt.Errorf("invalid audio input: %w", err)
	}

	tempDir, err := f.CreateTempDirectory(procCtx)
	if err != nil {
		return nil, fmt.Errorf("failed to create temp directory: %w", err)
	}
	defer f.CleanupTempDirectory(tempDir)

	// Build command
	outputFile := filepath.Join(tempDir, "result.json")
	scriptPath := filepath.Join(f.envPath, "foxnose", "foxnose_diarize.py")
	pythonPath := f.getASREnvPython()

	args := []string{scriptPath, input.FilePath, "--output", outputFile}

	if minSpeakers := f.GetIntParameter(params, "min_speakers"); minSpeakers > 0 {
		args = append(args, "--min-speakers", strconv.Itoa(minSpeakers))
	}
	if maxSpeakers := f.GetIntParameter(params, "max_speakers"); maxSpeakers > 0 {
		args = append(args, "--max-speakers", strconv.Itoa(maxSpeakers))
	}

	cmd := exec.CommandContext(ctx, pythonPath, args...)
	cmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

	// Log file
	logFile, err := os.OpenFile(filepath.Join(procCtx.OutputDirectory, "transcription.log"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer logFile.Close()
		cmd.Stdout = logFile
		cmd.Stderr = logFile
	}

	logger.Info("Executing FoxNose diarization", "python", pythonPath, "audio", input.FilePath)

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.Canceled {
			return nil, fmt.Errorf("diarization was cancelled")
		}
		logPath := filepath.Join(procCtx.OutputDirectory, "transcription.log")
		logTail, _ := f.ReadLogTail(logPath, 2048)
		return nil, fmt.Errorf("FoxNose diarization failed: %w\nLogs:\n%s", err, logTail)
	}

	// Parse JSON result (same format as pyannote JSON)
	result, err := f.parseResult(outputFile)
	if err != nil {
		return nil, fmt.Errorf("failed to parse result: %w", err)
	}

	result.ProcessingTime = time.Since(startTime)
	result.ModelUsed = "foxnose/diarize"
	result.Metadata = f.CreateDefaultMetadata(params)

	logger.Info("FoxNose diarization completed",
		"segments", len(result.Segments),
		"speakers", result.SpeakerCount,
		"processing_time", result.ProcessingTime)

	return result, nil
}

func (f *FoxNoseAdapter) parseResult(resultFile string) (*interfaces.DiarizationResult, error) {
	data, err := os.ReadFile(resultFile)
	if err != nil {
		return nil, fmt.Errorf("failed to read result: %w", err)
	}

	var foxResult struct {
		Segments []struct {
			Start      float64 `json:"start"`
			End        float64 `json:"end"`
			Speaker    string  `json:"speaker"`
			Confidence float64 `json:"confidence"`
		} `json:"segments"`
		Speakers     []string `json:"speakers"`
		SpeakerCount int      `json:"speaker_count"`
	}

	if err := json.Unmarshal(data, &foxResult); err != nil {
		return nil, fmt.Errorf("failed to parse JSON: %w", err)
	}

	result := &interfaces.DiarizationResult{
		Segments:     make([]interfaces.DiarizationSegment, len(foxResult.Segments)),
		SpeakerCount: foxResult.SpeakerCount,
		Speakers:     foxResult.Speakers,
	}

	for i, seg := range foxResult.Segments {
		result.Segments[i] = interfaces.DiarizationSegment{
			Start:      seg.Start,
			End:        seg.End,
			Speaker:    seg.Speaker,
			Confidence: seg.Confidence,
		}
	}

	return result, nil
}

func (f *FoxNoseAdapter) GetEstimatedProcessingTime(input interfaces.AudioInput) time.Duration {
	baseTime := f.BaseAdapter.GetEstimatedProcessingTime(input)
	return time.Duration(float64(baseTime) * 0.15) // ~8x faster than realtime
}
