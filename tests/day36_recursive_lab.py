def recursive_split(text: str, size: int, separators: list[str]) -> list[str]:
    """
    递归地分割文本，将文本分割成指定大小的块，每个块的末尾必须包含一个分隔符。
    Args:
        text: 要分割的文本
        size: 每个块的大小
        separators: 分隔符列表
    Returns:
        分割后的文本列表
    """
    result = []
    if text == "":  # 空文本
        return result
    if 0 < len(text) <= size:  # 文本长度大于并且小于等于 size，直接返回
        result.append(text)
        return result
    if len(separators) == 0:
        raise ValueError("分隔符列表不能为空")
    if separators[0] == "":
        length = len(text)
        for i in range(0, length, size):
            end = i + size
            if end > length:
                end = length
            result.append(text[i:end])
            if end == length:
                break
        return result
    if separators[0] not in text:
        result.extend(recursive_split(text, size, separators[1:]))
        return result
    split_text = text.split(separators[0])
    length = len(split_text)
    for i in range(length):
        piece = split_text[i]
        if i == length - 1 and piece == "":
            continue
        full_piece = piece
        if i != length - 1:
            full_piece += separators[0]

        if len(full_piece) <= size:
            result.append(full_piece)
        else:
            result.extend(recursive_split(full_piece, size, separators[1:]))
    return result
