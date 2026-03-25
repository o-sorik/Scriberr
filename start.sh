#!/bin/bash
# Start Scriberr with Ollama
# Ollama starts on demand and stops when Scriberr exits

echo "Starting Ollama..."
brew services start ollama 2>/dev/null
sleep 1

echo "Starting Scriberr → http://localhost:8080"
cd ~/asr-env && ~/Documents/Claude/scriberr/scriberr

echo "Stopping Ollama..."
brew services stop ollama 2>/dev/null
