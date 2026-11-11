from types import SimpleNamespace

import pytest

from desktop.backend.worker import qwen_attention as compat


def install(monkeypatch, errors=(), *, device="cuda:0", backend="sdpa", setter=True):
    calls, switches, warnings = [], [], []
    pending = iter(errors)
    class Referee:
        def _run_generate(self, inputs, budget):
            calls.append((inputs, budget))
            error = next(pending, None)
            if error is not None:
                raise error
            return "verified-output"
    config = SimpleNamespace(_attn_implementation=backend)
    model = SimpleNamespace(device=device, dtype="bf16", config=config)
    def set_attention(value):
        switches.append(value)
        config._attn_implementation = value
    if setter:
        model.set_attn_implementation = set_attention
    flags = SimpleNamespace(**{f"{name}_sdp_enabled": lambda: True for name in ("flash", "math", "mem_efficient", "cudnn")})
    loaded = {"finesub.speech.verification.qwen_referee": SimpleNamespace(QwenReferee=Referee),
              "torch": SimpleNamespace(backends=SimpleNamespace(cuda=flags))}
    monkeypatch.setattr(compat, "version", lambda name: {"torch": "2.11.0+cu128", "transformers": "5.14.1"}[name])
    monkeypatch.setattr(compat, "import_module", loaded.__getitem__)
    monkeypatch.setattr(compat, "current_reporter", lambda: SimpleNamespace(warning=lambda *args, **kwargs: warnings.append((args, kwargs))))
    compat.configure_qwen_attention()
    original_wrapper = Referee._run_generate
    compat.configure_qwen_attention()
    assert Referee._run_generate is original_wrapper
    instance = Referee()
    instance._model = model
    return instance, calls, switches, warnings


@pytest.mark.parametrize("message", ["No available kernel. Aborting execution.", "No viable backend for scaled_dot_product_attention was found."])
def test_kernel_failure_retries_once_without_changing_input_or_budget(monkeypatch, message):
    model, calls, switches, warnings = install(monkeypatch, [RuntimeError(message)])
    inputs = {"input_ids": SimpleNamespace(shape=(2, 45))}
    assert model._run_generate(inputs, 256) == "verified-output"
    assert calls == [(inputs, 256), (inputs, 256)]
    assert switches == ["eager"]
    assert len(warnings) == 2 and "input_shape=(2, 45)" in warnings[0][0][1]
    assert "qwen-attention-recovered" == warnings[1][0][0]
    assert model._run_generate(inputs, 128) == "verified-output"
    assert switches == ["eager"]  # Reused model stays compatible; no repeated setup.


@pytest.mark.parametrize("error", [RuntimeError("CUDA out of memory"), ValueError("bad audio"), RuntimeError("CUDA device-side assert")])
def test_unrelated_errors_keep_identity_and_are_not_retried(monkeypatch, error):
    model, calls, switches, warnings = install(monkeypatch, [error])
    with pytest.raises(type(error)) as caught:
        model._run_generate({}, 128)
    assert caught.value is error
    assert len(calls) == 1 and switches == [] and warnings == []


@pytest.mark.parametrize("device,backend", [("cpu", "sdpa"), ("cuda:0", "eager")])
def test_cpu_or_already_compatible_model_is_not_retried(monkeypatch, device, backend):
    error = RuntimeError("No available kernel")
    model, calls, switches, _ = install(monkeypatch, [error], device=device, backend=backend)
    with pytest.raises(RuntimeError) as caught:
        model._run_generate({}, 128)
    assert caught.value is error and len(calls) == 1 and not switches


def test_second_kernel_failure_is_actionable_and_finite(monkeypatch):
    model, calls, switches, warnings = install(monkeypatch, [RuntimeError("No available kernel")] * 3)
    with pytest.raises(RuntimeError, match="未跳过校验"):
        model._run_generate({}, 128)
    assert len(calls) == 2 and switches == ["eager"] and len(warnings) == 1


def test_oom_during_retry_is_not_misreported_as_recovered(monkeypatch):
    error = RuntimeError("CUDA out of memory during compatibility retry")
    model, calls, _, warnings = install(monkeypatch, [RuntimeError("No available kernel"), error])
    with pytest.raises(RuntimeError) as caught:
        model._run_generate({}, 128)
    assert caught.value is error and len(calls) == 2 and len(warnings) == 1


def test_successful_normal_inference_is_unchanged(monkeypatch):
    model, calls, switches, warnings = install(monkeypatch)
    assert model._run_generate({}, 128) == "verified-output"
    assert len(calls) == 1 and not switches and not warnings


@pytest.mark.parametrize("torch_version,transformers_version", [("2.12.0", "5.14.1"), ("2.11.0", "5.15.0")])
def test_only_pinned_runtime_is_patched(monkeypatch, torch_version, transformers_version):
    monkeypatch.setattr(compat, "version", lambda name: {"torch": torch_version, "transformers": transformers_version}[name])
    monkeypatch.setattr(compat, "import_module", lambda *_args: pytest.fail("unsupported runtime must not import models"))
    compat.configure_qwen_attention()


def test_lightweight_workers_do_not_import_torch(monkeypatch):
    def absent(_name):
        raise compat.PackageNotFoundError("torch")
    monkeypatch.setattr(compat, "version", absent)
    monkeypatch.setattr(compat, "import_module", lambda *_args: pytest.fail("no speech imports"))
    compat.configure_qwen_attention()


def test_unrelated_runtime_error_does_not_inspect_a_failed_model(monkeypatch):
    error = RuntimeError("CUDA out of memory")
    model, _, _, _ = install(monkeypatch, [error])
    model._model = object()
    with pytest.raises(RuntimeError) as caught:
        model._run_generate({}, 128)
    assert caught.value is error


@pytest.mark.parametrize("missing", ["finesub.speech.verification.qwen_referee", "numpy"])
def test_only_missing_legacy_referee_is_optional(monkeypatch, missing):
    monkeypatch.setattr(compat, "version", lambda name: {"torch": "2.11.0", "transformers": "5.14.1"}[name])
    def absent(_name):
        raise ModuleNotFoundError("missing", name=missing)
    monkeypatch.setattr(compat, "import_module", absent)
    if missing == "numpy":
        with pytest.raises(ModuleNotFoundError):
            compat.configure_qwen_attention()
    else:
        compat.configure_qwen_attention()
