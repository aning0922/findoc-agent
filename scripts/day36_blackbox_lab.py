from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters import CharacterTextSplitter
from langchain_text_splitters import TokenTextSplitter
import tiktoken

splitter = RecursiveCharacterTextSplitter(
    chunk_size=12,
    chunk_overlap=0,
    separators=["\n\n", "\n", "。", ""],
    keep_separator="end",
    length_function=len,
    strip_whitespace=False,
)

source_text = """摘要完整。

收入增长
成本下降。海外订单ABCDEFGHIJKLMNO"""

result = splitter.split_text(source_text)
for i, chunk in enumerate(result):
    print(f"recursive-char：{i}: {repr(chunk)}: {len(chunk)}")

char_splitter = CharacterTextSplitter(
    separator="", chunk_size=12, chunk_overlap=0, length_function=len, strip_whitespace=False
)
result = char_splitter.split_text(source_text)
for i, chunk in enumerate(result):
    print(f"fixed-char：{i}: {repr(chunk)}: {len(chunk)}")

encoding = tiktoken.get_encoding("cl100k_base")
texts = ["财务报告", "ABCDEFGHIJKLMNO", "财务报告ABC123😊", source_text]

for sample in texts:
    tokens = encoding.encode(sample)
    print(
        f"token_encoding:  text: {repr(sample)} len: {len(sample)} tokens: {tokens} tokens_len: {len(tokens)}"
    )

tiktoken_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="cl100k_base",
    chunk_size=12,
    chunk_overlap=0,
    separators=["\n\n", "\n", "。", ""],
    keep_separator="end",
    strip_whitespace=False,
)


tiktoken_result = tiktoken_splitter.split_text(source_text)
for i, chunk in enumerate(tiktoken_result):
    print(
        f"recursive-token: index: {i} text: {repr(chunk)} len: {len(chunk)} token_count: {len(encoding.encode(chunk))}"
    )


char_overlap_splitter = CharacterTextSplitter(
    separator="", chunk_size=12, chunk_overlap=3, length_function=len, strip_whitespace=False
)
result = char_overlap_splitter.split_text(source_text)
for i, chunk in enumerate(result):
    print(f"fixed-char-overlap3：{i}: {repr(chunk)}: {len(chunk)}")


sentence_splitter = RecursiveCharacterTextSplitter(
    chunk_size=12,
    chunk_overlap=0,
    separators=["。", "\n\n", "\n", ""],
    keep_separator="end",
    length_function=len,
    strip_whitespace=False,
)

result = sentence_splitter.split_text(source_text)
for i, chunk in enumerate(result):
    print(f"recursive-char-sentence-first：{i}: {repr(chunk)}: {len(chunk)}")

no_separator_text = "甲乙丙丁戊己庚辛壬癸ABCDEFGHIJ"
no_separator_splitter = RecursiveCharacterTextSplitter(
    chunk_size=8,
    chunk_overlap=2,
    separators=["\n\n", "\n", "。", ""],
    keep_separator="end",
    length_function=len,
    strip_whitespace=False,
)

result = no_separator_splitter.split_text(no_separator_text)
for i, chunk in enumerate(result):
    print(f"break-no-separator：{i}: {repr(chunk)}: {len(chunk)}")

tiny_text = "财务报告"
tiny_token_hard_splitter = TokenTextSplitter(
    encoding_name="cl100k_base", chunk_size=1, chunk_overlap=0
)

chunks = tiny_token_hard_splitter.split_text(tiny_text)
for i, chunk in enumerate(chunks):
    print(
        f"tiny-token-hard：{i}: {repr(chunk)}: {len(chunk)} tokens: {len(encoding.encode(chunk))}"
    )
print(f"tiny-token-hard: {''.join(chunks) == '财务报告'}")

tiny_token_recursive_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="cl100k_base",
    chunk_size=1,
    chunk_overlap=0,
    separators=[""],
    strip_whitespace=False,
)
chunks = tiny_token_recursive_splitter.split_text(tiny_text)
for i, chunk in enumerate(chunks):
    print(
        f"tiny-token-recursive：{i}: {repr(chunk)}: {len(chunk)} tokens: {len(encoding.encode(chunk))}"
    )
print(f"tiny-token-recursive: {''.join(chunks) == '财务报告'}")


break_whitespace_preserve_splitter = CharacterTextSplitter(
    separator="",
    chunk_size=3,
    chunk_overlap=0,
    strip_whitespace=False,
)

test_text1 = ""
test_text2 = "  \n\t "


chunks = break_whitespace_preserve_splitter.split_text(test_text1)
print(f"break-whitespace-preserve text1: {repr(test_text1)} chunks: {chunks}")

chunks = break_whitespace_preserve_splitter.split_text(test_text2)
print(f"break-whitespace-preserve text2: {repr(test_text2)} chunks: {chunks}")


break_whitespace_strip_splitter = CharacterTextSplitter(
    separator="",
    chunk_size=3,
    chunk_overlap=0,
    strip_whitespace=True,
)

chunks = break_whitespace_strip_splitter.split_text(test_text1)
print(f"break-whitespace-strip text1: {repr(test_text1)} chunks: {chunks}")

chunks = break_whitespace_strip_splitter.split_text(test_text2)
print(f"break-whitespace-strip text2: {repr(test_text2)} chunks: {chunks}")

mixed_text = "财报ABC123😊增长"
break_mixed_splitter = CharacterTextSplitter(
    separator="",
    chunk_size=4,
    chunk_overlap=1,
    strip_whitespace=False,
)

chunks = break_mixed_splitter.split_text(mixed_text)
for i, chunk in enumerate(chunks):
    print(f"break-mixed：index: {i} text: {repr(chunk)} len: {len(chunk)} tokens: {len(encoding.encode(chunk))}")


gate_unseen_text = """现金充足。

应收账款上升
海外客户ABCDEFGHIJK"""

gate_unseen_splitter = RecursiveCharacterTextSplitter(
    length_function=len,
    chunk_size=10,
    chunk_overlap=2,
    separators=["\n\n", "\n", "。", ""],
    keep_separator="end",
    strip_whitespace=False,
)

chunks = gate_unseen_splitter.split_text(gate_unseen_text)
for i, chunk in enumerate(chunks):
    print(f"gate-unseen：index: {i} text: {repr(chunk)} len: {len(chunk)} tokens: {len(encoding.encode(chunk))}")