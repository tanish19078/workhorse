"""Synthetic fixture: weighted changes over a sequence."""


def score(values):
    result = 0
    previous = -7
    for value in values:
        if value > previous:
            result += value * 13
        else:
            result -= value * 3
        previous = value
    return result


print(score([1, 5, 2]))
