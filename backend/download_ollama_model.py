import argparse
import json
import os
import urllib.request


REGISTRY = "registry.ollama.ai"


def _ollama_models_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".ollama", "models")


def _blob_dest_path(sha256_hex: str) -> str:
    return os.path.join(_ollama_models_dir(), "blobs", f"sha256-{sha256_hex}")


def _manifest_dest_path(model_name: str, tag: str) -> str:
    # Ollama stores manifests under:
    # ~/.ollama/models/manifests/registry.ollama.ai/library/<model>/<tag>
    return os.path.join(
        _ollama_models_dir(),
        "manifests",
        REGISTRY,
        "library",
        model_name,
        tag,
    )


def _download_json(url: str, accept: str | None = None) -> dict:
    headers = {}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())


def _download_to_file(url: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path + ".partial"):
        os.remove(dest_path + ".partial")
    tmp_path = dest_path + ".partial"
    urllib.request.urlretrieve(url, tmp_path)
    os.replace(tmp_path, dest_path)


def _install_from_local_blob(sha256_hex: str, expected_size: int | None, dest_path: str) -> bool:
    # If the user already downloaded blobs into the current working directory
    # with filename equal to the sha256 hex, reuse them.
    local_path = os.path.join(os.getcwd(), sha256_hex)
    if not os.path.exists(local_path):
        return False

    if expected_size is not None:
        try:
            actual_size = os.path.getsize(local_path)
        except OSError:
            return False
        if actual_size != expected_size:
            return False

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    os.replace(local_path, dest_path)
    return True


def download_and_install_model(model_name: str, tag: str) -> None:
    manifest_url = f"https://{REGISTRY}/v2/library/{model_name}/manifests/{tag}"
    manifest = _download_json(
        manifest_url,
        accept="application/vnd.docker.distribution.manifest.v2+json",
    )

    layers = manifest.get("layers", [])
    config = manifest.get("config") or {}
    config_digest = config.get("digest")

    print(f"Manifest downloaded. Layers: {len(layers)}")
    if config_digest:
        print(f"Config digest: {config_digest}")
        #We are in collab

    # Download config blob (required)
    if config_digest and config_digest.startswith("sha256:"):
        cfg_sha = config_digest.replace("sha256:", "")
        cfg_dest = _blob_dest_path(cfg_sha)
        if not os.path.exists(cfg_dest):
            print(f"Downloading config {cfg_sha[:16]}...")
            cfg_url = f"https://{REGISTRY}/v2/library/{model_name}/blobs/{config_digest}"
            _download_to_file(cfg_url, cfg_dest)
            print(f"  Saved to {cfg_dest}")

    # Download each layer blob into ~/.ollama/models/blobs/
    for layer in layers:
        digest = layer["digest"]
        if not digest.startswith("sha256:"):
            raise ValueError(f"Unsupported digest format: {digest}")

        sha256_hex = digest.replace("sha256:", "")
        expected_size = layer.get("size")
        size_mb = ((expected_size or 0) / 1024 / 1024) if expected_size else 0.0
        dest_path = _blob_dest_path(sha256_hex)

        if os.path.exists(dest_path):
            print(f"Blob exists {sha256_hex[:16]}... skipping")
            continue

        if _install_from_local_blob(sha256_hex=sha256_hex, expected_size=expected_size, dest_path=dest_path):
            print(f"Installed from local file {sha256_hex[:16]}... -> {dest_path}")
            continue

        url = f"https://{REGISTRY}/v2/library/{model_name}/blobs/{digest}"
        print(f"Downloading {sha256_hex[:16]}... ({size_mb:.1f} MB)")
        _download_to_file(url, dest_path)
        print(f"  Saved to {dest_path}")

    # Write manifest to ~/.ollama/models/manifests/... so `ollama list` can see it
    manifest_path = _manifest_dest_path(model_name, tag)
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    print(f"Manifest installed to {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="llama3.2")
    parser.add_argument("--tag", default="1b")
    args = parser.parse_args()

    os.makedirs(os.path.join(_ollama_models_dir(), "blobs"), exist_ok=True)
    os.makedirs(os.path.join(_ollama_models_dir(), "manifests"), exist_ok=True)

    download_and_install_model(model_name=args.model, tag=args.tag)


if __name__ == "__main__":
    main()