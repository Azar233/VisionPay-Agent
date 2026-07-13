from huggingface_hub import snapshot_download

DATA_ROOT = "/data0/xshi/datasets/visionpay"

snapshot_download(
    repo_id="benjamintli/retail-product-checkout",
    repo_type="dataset",
    local_dir=f"{DATA_ROOT}/raw/hf_rpc",
    cache_dir=f"{DATA_ROOT}/hf_cache",
    allow_patterns=["data/*.parquet", "README.md", ".gitattributes"],
    max_workers=8,
)
print("HF RPC snapshot download finished")
