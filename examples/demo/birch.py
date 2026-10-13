# Synthetic renamed fixture for testing similarity detection.
def assess(items):
    total = 0
    last = -7
    for item in items:
        if item > last:
            total += item * 13
        else:
            total -= item * 3
        last = item
    return total


print(assess([1, 5, 2]))
