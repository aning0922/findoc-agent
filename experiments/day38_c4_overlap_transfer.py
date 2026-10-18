from app.rag.chunk import count_tokens
from experiments.day38_b_experiment import (
    build_experiment_splitter,
    measure_source_coverage,
)

TEXT = "A B C D E F G H I J K L M N O P Q R S T U V W X"
CONFIGS = [
    ("T0", 8, 0),
    ("T3", 8, 3),
]


def main() -> None:
    for name, size, overlap in CONFIGS:
        splitter = build_experiment_splitter(size, overlap)
        pieces = splitter.split_text(TEXT)
        measurement = measure_source_coverage(TEXT, pieces)

        print(
            name,
            f"chunks={len(pieces)}",
            f"coverage={measurement['coverage_ratio']:.4f}",
            f"duplicate_chars={measurement['duplicate_chars']}",
        )

        for index, (piece, span) in enumerate(zip(pieces, measurement["start_and_end_list"])):
            print(
                f"  {index}:",
                f"tokens={count_tokens(piece)}",
                f"span={span}",
                repr(piece),
            )


if __name__ == "__main__":
    main()
