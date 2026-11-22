# Round 2 Runtime Resolution

Resolved 2026-07-27 on an Apple M4 Max host with 64 GB unified memory and arm64 macOS.

## Decisions

| Question | Resolution | Evidence and consequence |
| --- | --- | --- |
| DeepSeek-OCR 2 on Apple Silicon | Admit as a PDF-only MLX cell. | `mlx-community/DeepSeek-OCR-2-bf16` at commit `9946f9ac306378a3e6a86cad7d7f8be8e536f092`; 3,389,119,360 BF16 parameters and 6,788,542,168 cached model bytes. `mlx-vlm==0.6.7` needs a small direct processor-registration shim because its generic loader swallows an upstream processor exception. Five TI pages completed in 31.5 seconds. Office inputs are N/A by design. |
| dots.ocr on Apple Silicon | Admit as a PDF-only MLX cell, with model failures scored rather than hidden. | `mlx-community/dots.ocr-4bit` at commit `4ab989e403d4f8cafa5fdeede5b2290a706c2405`; 3,538,469,850 cached model bytes. The canonical Docling layout prompt through `mlx-vlm==0.6.7` completed five TI pages in 105.2 seconds. Four pages contained text and table markup; one returned layout boxes without text. Office inputs are N/A. |
| Docling ~3B VLM swap | Use an explicitly labeled hybrid fallback. | Docling 2.114.0 accepts `--pipeline vlm --vlm-model qwen --device mps` and resolves to `mlx-community/Qwen2.5-VL-3B-Instruct-bf16`, but the one-page native smoke conversion exited zero with only an escaped chat-control token. The same checkpoint worked directly through MLX. The admitted cell therefore reuses the locked round-one Docling structure and appends standalone Qwen 3B descriptions for the verified visual units. It is not represented as a native Docling swap. |
| 7B+ local ceiling | Admit a standalone Qwen visual pass over the same reused structure. | `mlx-community/Qwen2.5-VL-7B-Instruct-4bit` at commit `fdcc572e8b05ba9daeaf71be8c9e4267c826ff9b`; 5,653,491,418 cached model bytes. The harness uses identical visual units and prompts to the 3B hybrid. |
| Third judge family | Run the two-family minimum panel. | `gemini` is not installed on this host, so no authenticated Gemini CLI is available. Claude and Codex each judge every pair. This limitation must remain visible in the findings. |

## Pins and Caveats

The common local runner is `mlx-vlm==0.6.7`. Qwen 3B is the BF16 checkpoint at commit `33765717028a7f0514ea1d213035cddf4b32c500` with 7,525,308,576 cached model bytes. The runner, model snapshots, prompts, raw page results, token counts, peak memory, and elapsed time are retained in the run artifacts.

Docling’s source preset makes the platform split explicit: Qwen has a native MLX preset, DeepSeek-OCR is exposed through Ollama or LM Studio, and dots.ocr defaults to vLLM. The standalone MLX cells are therefore harness variants, not claims that Docling natively supports those two paths on Apple Silicon.

MinerU 2.5 remains deferred because it is a separate heavy pipeline rather than a trivial addition to this ladder. Marker remains deferred because of its GPL licensing and because it is not needed to answer the precommitted local-model question.
