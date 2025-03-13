def list_to_tuple(value, string=False):
    result = None
    if value:
        if string:
            result = "('" + "', '".join(map(str, value)) + "')"
        else:
            result = "(" + ", ".join(map(str, value)) + ")"
    return result
