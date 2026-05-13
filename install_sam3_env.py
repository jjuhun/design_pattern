#!/usr/bin/env python3
"""
KITECH_Segmentation - SAM3 설치/확인 스크립트

역할:
1. 현재 Python/conda 환경 확인
2. SAM3 실행에 필요한 HuggingFace 패키지 설치
3. PyTorch CUDA 사용 가능 여부 확인
4. HuggingFace 로그인 상태 확인
5. SAM3 모델 다운로드/cache 로드 테스트

사용법:
    conda activate kitech_segmentation
    python install_sam3_env.py

주의:
- facebook/sam3 계정 접근 승인이 필요합니다.
- HuggingFace 토큰 로그인이 안 되어 있으면 아래 명령을 먼저 실행하세요.
    hf auth login --force
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_PIP_PACKAGES = [
    "transformers",
    "huggingface_hub",
    "accelerate",
    "safetensors",
]

# 현재 프로젝트에서 테스트했던 SAM3 HF repo 이름.
# 사용 중인 코드에서 다른 repo id를 쓰면 여기만 바꾸면 됩니다.
SAM3_REPO_ID_CANDIDATES = [
    "facebook/sam3-hiera-large",
    "facebook/sam3",
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("\n$ " + " ".join(cmd))
    return subprocess.run(cmd, check=check)


def module_exists(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def install_required_packages() -> None:
    missing = []
    module_map = {
        "transformers": "transformers",
        "huggingface_hub": "huggingface_hub",
        "accelerate": "accelerate",
        "safetensors": "safetensors",
    }

    for pkg in REQUIRED_PIP_PACKAGES:
        if not module_exists(module_map[pkg]):
            missing.append(pkg)

    if not missing:
        print("\n[OK] SAM3 관련 pip 패키지가 이미 설치되어 있습니다.")
        return

    print("\n[INFO] 누락된 패키지를 설치합니다:", ", ".join(missing))
    run([sys.executable, "-m", "pip", "install", "-U", *missing])


def check_torch_cuda() -> None:
    print("\n[INFO] PyTorch/CUDA 상태 확인")
    try:
        import torch
    except Exception as exc:
        print("[ERROR] torch import 실패:", exc)
        print("       conda 환경에 pytorch, torchvision, pytorch-cuda=12.1을 설치하세요.")
        return

    print(f"  torch: {torch.__version__}")
    print(f"  cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  cuda device: {torch.cuda.get_device_name(0)}")
    else:
        print("[WARN] CUDA를 사용할 수 없습니다. 현재 프로젝트 SAM 기능은 GPU 기준입니다.")


def check_hf_login() -> bool:
    print("\n[INFO] HuggingFace 로그인 상태 확인")
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        user = api.whoami()
        name = user.get("name") or user.get("email") or "unknown"
        print(f"[OK] HuggingFace 로그인됨: {name}")
        return True
    except Exception as exc:
        print("[WARN] HuggingFace 로그인 확인 실패:")
        print(f"       {exc}")
        print("\n다음 명령을 실행한 뒤 다시 시도하세요:")
        print("    hf auth login --force")
        print("\n또는 예전 CLI라면:")
        print("    huggingface-cli login")
        return False


def try_load_sam3() -> None:
    print("\n[INFO] SAM3 모델 다운로드/cache 로드 테스트")
    print("      최초 실행이면 모델 파일을 HuggingFace cache로 다운로드합니다.")

    try:
        import torch
        from transformers import Sam3Model, Sam3Processor
    except Exception as exc:
        print("[ERROR] transformers SAM3 import 실패:", exc)
        print("       transformers 버전이 낮으면 업데이트가 필요합니다.")
        return

    last_error: Exception | None = None
    for repo_id in SAM3_REPO_ID_CANDIDATES:
        print(f"\n[TRY] {repo_id}")
        try:
            processor = Sam3Processor.from_pretrained(repo_id)
            model = Sam3Model.from_pretrained(repo_id)
            if torch.cuda.is_available():
                model = model.to("cuda")
            model.eval()
            print(f"[OK] SAM3 로드 성공: {repo_id}")
            print("[OK] 다음부터는 ~/.cache/huggingface/hub/ cache를 사용합니다.")
            del processor
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return
        except Exception as exc:
            last_error = exc
            print(f"[FAIL] {repo_id}")
            print(f"       {exc}")

    print("\n[ERROR] SAM3 로드 실패")
    print("가능한 원인:")
    print("  1. HuggingFace 로그인이 안 됨")
    print("  2. facebook/sam3 접근 승인이 안 됨")
    print("  3. 인터넷 연결 문제")
    print("  4. transformers 버전이 SAM3를 아직 지원하지 않음")
    if last_error is not None:
        print("\n마지막 오류:")
        print(last_error)


def main() -> None:
    print("=" * 70)
    print("KITECH_Segmentation SAM3 설치/확인")
    print("=" * 70)
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version.split()[0]}")
    print(f"CONDA_PREFIX: {os.environ.get('CONDA_PREFIX', '(not conda)')}")

    if sys.version_info[:2] != (3, 10):
        print("\n[WARN] 권장 Python 버전은 3.10입니다.")

    install_required_packages()
    check_torch_cuda()

    logged_in = check_hf_login()
    if not logged_in:
        print("\n[STOP] 로그인 후 다시 실행하세요.")
        return

    try_load_sam3()

    print("\n[DONE] 설치/확인 스크립트 종료")


if __name__ == "__main__":
    main()
