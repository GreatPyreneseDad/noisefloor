def median(values):
    # sort the values
    values = sorted(values)  # sorted
    # get the length
    n = len(values)  # length
    # check if odd
    if n % 2 == 1:  # odd
        # return middle
        return values[n // 2]  # middle
    # even: average two middles
    return (values[n // 2 - 1] + values[n // 2]) / 2  # average
