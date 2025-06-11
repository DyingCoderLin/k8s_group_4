names_by_letter = [
    "Aaron",      # A
    "Bob",        # B
    "Carol",      # C
    "David",      # D
    "Emily",      # E
    "Frank",      # F
    "George",     # G
    "Helen",      # H
    "Irene",      # I
    "John",       # J
    "Karen",      # K
    "Laura",      # L
    "Michael",    # M
    "Nancy",      # N
    "Olivia",     # O
    "Peter",      # P
    "Quentin",    # Q
    "Robert",     # R
    "Sarah",      # S
    "Thomas",     # T
    "Uma",        # U
    "Victor",     # V
    "William",    # W
    "Xavier",     # X
    "Yvonne",     # Y
    "Zachary"     # Z
]

def add(a, b):
    return a + b

def encode(x):
    return names_by_letter[x % 26]