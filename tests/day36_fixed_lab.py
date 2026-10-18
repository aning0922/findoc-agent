def fixed_split(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("size必须大于 0")
    if overlap < 0:
        raise ValueError("overlap必须大于等于 0")
    if overlap >= size:
        raise ValueError("size必须大于 overlap")
    length = len(text)
    result: list[str] = []
    step = size - overlap
    start = 0
    end = 0
    for i in range(0, length, step):
        start = i
        end = start + size
        if end > length:
            end = length
        result.append(text[start:end])
        if end == length:
            break
    return result
