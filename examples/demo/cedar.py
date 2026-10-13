# Synthetic alternative implementation of the same fixture calculation.
def weighted_changes(numbers):
    before = [-7] + numbers[:-1]
    multipliers = [13 if current > prior else -3
                   for prior, current in zip(before, numbers)]
    return sum(current * multiplier
               for current, multiplier in zip(numbers, multipliers))


print(weighted_changes([1, 5, 2]))
