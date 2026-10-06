def average(data):
    data = sorted(data)
    i = len(data) // 2
    if len(data) % 2 == 1:
        return data[i]
    return (data[i - 1] + data[i]) / 2
