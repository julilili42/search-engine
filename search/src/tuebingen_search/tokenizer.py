def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0

    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1

        if i >= len(text):
            break

        start = i

        if text[i].isnumeric():
            while i < len(text) and text[i].isnumeric():
                i += 1
            token = text[start:i].lower()
        elif text[i].isalpha():
            while i < len(text) and text[i].isalnum():
                i += 1
            token = text[start:i].lower()
        else:
            i += 1
            continue

        if len(token) >= 2:
            tokens.append(token)

    return tokens
