"""Worker-local compatibility for the pinned Qwen/Transformers attention path."""
from __future__ import annotations

from functools import wraps
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

from finesub.reporting import current_reporter


def _kernel_unavailable(error: RuntimeError) -> bool:
    message = str(error).lower()
    return "no available kernel" in message or "no viable backend for scaled_dot_product_attention" in message


def configure_qwen_attention() -> None:
    try:
        versions = (version("torch").split("+", 1)[0], version("transformers"))
    except PackageNotFoundError:
        return  # LLM-only workers need not install the speech stack.
    if versions != ("2.11.0", "5.14.1"):
        return
    try:
        module = import_module("finesub.speech.verification.qwen_referee")
    except ModuleNotFoundError as error:
        if error.name == "finesub.speech.verification.qwen_referee":
            return
        raise
    # shortcut: pinned private Qwen method; revalidate when updating the core/runtime.
    original = module.QwenReferee._run_generate
    if getattr(original, "_yanami_attention_compat", False):
        return
    torch = import_module("torch")

    @wraps(original)
    def generate(self, inputs, budget):
        try:
            return original(self, inputs, budget)
        except RuntimeError as error:
            if not _kernel_unavailable(error):
                raise
            model = self._model
            device = str(model.device)
            backend = getattr(model.config, "_attn_implementation", "unknown")
            if not device.startswith("cuda") or backend == "eager":
                raise
            shape = tuple(getattr(inputs.get("input_ids"), "shape", ()))
            flags = {name: getattr(torch.backends.cuda, f"{name}_sdp_enabled")()
                     for name in ("flash", "math", "mem_efficient", "cudnn")}
            current_reporter().warning(
                "qwen-attention-compat",
                f"Qwen 注意力内核不可用，改用本模型的兼容注意力重试一次 / "
                f"Qwen attention kernel unavailable; retrying once with model-local eager attention. "
                f"device={device} dtype={model.dtype} input_shape={shape} backend={backend} sdpa={flags}",
                impact="继续执行校验，不跳过；可能稍慢或增加显存 / Verification is retained; may use more time or VRAM",
            )
            # Do not change process-wide SDP flags: batch separation may run on another thread.
            model.set_attn_implementation("eager")
            try:
                result = original(self, inputs, budget)
            except RuntimeError as retry_error:
                if _kernel_unavailable(retry_error):
                    raise RuntimeError(
                        "Qwen 兼容注意力重试仍失败，任务已停止，未跳过校验。请保留日志与任务后重试；"
                        "临时关闭第二模型校验会降低补漏能力。 / "
                        "Qwen attention compatibility retry failed; verification was not skipped."
                    ) from retry_error
                raise
            current_reporter().warning(
                "qwen-attention-recovered",
                f"Qwen 兼容注意力重试成功，后续校验继续使用 eager（{device}） / "
                f"Qwen attention recovered; continuing verification with eager on {device}",
            )
            return result

    generate._yanami_attention_compat = True
    module.QwenReferee._run_generate = generate
