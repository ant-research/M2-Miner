#!/bin/bash
export CUDA_VISIBLE_DEVICES=0

model_path="model path"
host="the host where the model is deployed"
port="service port"

vllm serve "${model_path}" \
	--host "${host}" \
	--port "${port}" \
	--uvicorn-log-level "info"
