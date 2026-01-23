

import csv

def compteur(n):
    return [(n >> i) & 1 for i in reversed(range(8))]

def bit3(n) : 
    return [(n >> i) & 1 for i in reversed(range(3))]




def sortie(n) : 
    k = 7
    while k >= 0 : 
        if compteur(n)[k] == 0 : 
            return [int(i == k) for i in range(8)] + bit3(7-k) 
        k -= 1
    return [0]*8 + [0]*3
    
    


def exporter_csv(nom="table_verite.csv"):
    with open(nom, "w", newline="") as f:
        writer = csv.writer(f)

        # En-tête avec séparations
        writer.writerow(
            [f"E{i}" for i in range(8)] +
            ["|"] +
            [f"WE{i}" for i in range(8)] +
            ["||"] +
            ["Sel2", "Sel1", "Sel0"]
        )

        for n in range(256):
            writer.writerow(
                compteur(n) +
                ["|"] +
                sortie(n)[:8] +
                ["||"] +
                sortie(n)[8:]
            )


exporter_csv()

