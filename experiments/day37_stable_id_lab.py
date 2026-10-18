import hashlib
from experiments.day37_structure_lab import LabDocChunk
import json

def build_chunk_identity_payload(chunk: LabDocChunk, source_locator: str) -> str:
    """
    构建chunk的唯一标识payload
    """
    if source_locator == "" or source_locator is None:
        raise ValueError("source_locator 丢失")
    if chunk.source_file is None or chunk.source_file == "":
        raise ValueError("source_file 丢失")

    data_dict = {
        "source_locator": source_locator,
        "source_file": chunk.source_file,
        "page": chunk.page,
        "text": chunk.text,
        "section": chunk.section,
    }
    return json.dumps(data_dict, ensure_ascii=False, sort_keys=True)


def build_stable_chunk_id(chunk: LabDocChunk, source_locator: str) -> str:
    """
    根据chunk和source_locator生成稳定ID
    """
    json_data = build_chunk_identity_payload(chunk, source_locator)
    return hashlib.sha256(json_data.encode('utf-8')).hexdigest()
