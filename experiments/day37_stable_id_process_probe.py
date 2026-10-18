from experiments.day37_stable_id_lab import build_stable_chunk_id
from experiments.day37_structure_lab import LabDocChunk

def process_probe(chunk: LabDocChunk) -> str:
    return build_stable_chunk_id(chunk, "element-a")


if __name__ == "__main__":
    chunk = LabDocChunk(
        text="Hello, world!",
        page=1,
        type="paragraph",
        source_file="demo.pdf",
        table_md="",
        section="",
        chunk_id="",
    )
    print(process_probe(chunk))