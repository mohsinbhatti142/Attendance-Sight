"""
CUDA & NVIDIA GPU Environment Configuration.

Ensures NVIDIA discrete GPU (Quadro P5000) is prioritized over Intel HD Graphics.
Dynamically adds the packaged NVIDIA CUDA 12 / cuDNN 9 DLLs to the Windows DLL
search path so ONNX Runtime can initialize its CUDA execution provider.
"""
import os
import sys
import ctypes
from pathlib import Path

_DLL_HANDLES = []

def setup_cuda_env():
    """Load CUDA DLLs and configure NVIDIA GPU prioritization."""
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

    # CUDA/cuDNN wheels install DLLs into package-specific `nvidia/*/bin`
    # folders. Register those locations before ONNX Runtime is imported.
    nvidia_roots = [Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"]
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        nvidia_roots.insert(0, Path(bundled_root) / "nvidia")

    for nvidia_root in nvidia_roots:
        if not nvidia_root.is_dir():
            continue
        dll_paths = list(nvidia_root.glob("*/bin/*.dll"))
        for dll_path in dll_paths:
            dll_dir = str(dll_path.parent)
            if hasattr(os, "add_dll_directory"):
                _DLL_HANDLES.append(os.add_dll_directory(dll_dir))
            os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        # Preload the bundled CUDA dependencies so Windows resolves the
        # ONNX CUDA provider's transitive DLL references consistently.
        for dll_path in dll_paths:
            try:
                _DLL_HANDLES.append(ctypes.WinDLL(str(dll_path)))
            except (OSError, AttributeError):
                pass
    
    try:
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if os.path.exists(torch_lib):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(torch_lib)
            os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

setup_cuda_env()
