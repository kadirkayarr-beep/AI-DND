import game


def roll_d20():
    random = game._session().rng
    return random.randint(1, 20)
