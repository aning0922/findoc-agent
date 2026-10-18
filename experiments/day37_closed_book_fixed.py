def fixed_split(text: str, size: int, overlap:int) -> list[str]:
    if size <= 0:
        raise ValueError("size必须大于0")
    if overlap < 0:
        raise ValueError("overlap必须大于等于0")
    if overlap >= size:
        raise ValueError("overlap必须小于size")
    length = len(text)
    result: list[str] = []
    step = size - overlap
    for i in range(0, length, step):
        start = i
        end = start + size
        if end >= length:
            result.append(text[start:])
            break
        else:
            result.append(text[start:end])
    return result


if __name__ == "__main__":
    result = fixed_split("", 4, 1)
    print(result)
    result = fixed_split("ABC", 4, 1)
    print(result)
    result = fixed_split("ABCD", 4, 1)
    print(result)
    result = fixed_split("ABCDEFGHI", 4, 1)
    print(result)
    try:
        result = fixed_split("ABC", 0, 0)
        print(result)
    except ValueError as e:
        print(e)
    try:
        result = fixed_split("ABC", 4, -1)
        print(result)
    except ValueError as e:
        print(e)
    try:
        result = fixed_split("ABC", 4, 4)
        print(result)
    except ValueError as e:
        print(e)
