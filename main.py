import random

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

df = pd.read_csv("iot_dataset.csv", sep=r",|\s{2,}", engine="python")
df.replace("-", np.nan, inplace=True)
drop_cols = ["ts", "uid", "id.orig_h", "id.resp_h"]

df = df.drop(columns=drop_cols)
categorical_cols = [
    "proto",
    "service",
    "conn_state",
    "history",
    "local_orig",
    "local_resp",
]

encoders = {}

for col in categorical_cols:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col].astype(str))
    encoders[col] = le

print("Lable: ", df["label"].value_counts())
print("Detailed Lable: ", df["detailed-label"].value_counts())
label_column = "label"

label_encoder = LabelEncoder()
df[label_column] = label_encoder.fit_transform(df[label_column].astype(str))

X = df.drop(columns=[label_column])
y = df[label_column]

feature_names = list(X.columns)
X = X.values
y = y.values

print("Dataset shape:", X.shape)
print("Label distribution:")
print(pd.Series(y).value_counts())
print("Missing values:", df.isna().sum().sum())

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42
)

model = xgb.XGBClassifier()
model.load_model("xgb_model.json")


def select_features(X, chromosome):

    mask = chromosome.astype(bool)
    X_masked = X.copy()
    X_masked[:, ~mask] = 0
    return X_masked


def fitness_function(chromosome):

    if np.sum(chromosome) == 0:
        return 0
    X_selected = select_features(X_test, chromosome)
    predictions = model.predict(X_selected)
    score = f1_score(y_test, predictions, average="weighted")
    penalty = 0.002 * np.sum(chromosome)
    return score - penalty


def initialize_population(pop_size, chromosome_length):

    population = []
    for _ in range(pop_size):
        chromosome = np.random.randint(0, 2, chromosome_length)
        population.append(chromosome)

    return population


def tournament_selection(population, fitness_scores, k=3):
    selected = random.sample(list(zip(population, fitness_scores)), k)
    selected.sort(key=lambda x: x[1], reverse=True)
    return selected[0][0]


def crossover(parent1, parent2):
    point = random.randint(1, len(parent1) - 1)
    child1 = np.concatenate((parent1[:point], parent2[point:]))
    child2 = np.concatenate((parent2[:point], parent1[point:]))
    return child1, child2


def mutate(chromosome, mutation_rate):

    for i in range(len(chromosome)):
        if random.random() < mutation_rate:
            chromosome[i] = 1 - chromosome[i]

    return chromosome


def genetic_algorithm(
    pop_size, chromosome_length, generations, mutation_rate, crossover_rate
):
    population = initialize_population(pop_size, chromosome_length)
    best_chromosome = None
    best_score = -1

    for generation in range(generations):
        fitness_scores = [fitness_function(ch) for ch in population]
        gen_best = max(fitness_scores)
        if gen_best > best_score:
            best_score = gen_best
            best_chromosome = population[fitness_scores.index(gen_best)]

        print(f"Generation {generation} Best Fitness: {gen_best}")
        new_population = []
        while len(new_population) < pop_size:
            parent1 = tournament_selection(population, fitness_scores)
            parent2 = tournament_selection(population, fitness_scores)
            if random.random() < crossover_rate:
                child1, child2 = crossover(parent1, parent2)
            else:
                child1, child2 = parent1.copy(), parent2.copy()

            child1 = mutate(child1, mutation_rate)
            child2 = mutate(child2, mutation_rate)
            new_population.extend([child1, child2])
        population = new_population[:pop_size]

    return best_chromosome, best_score


chromosome_length = X.shape[1]
best_chromosome, best_score = genetic_algorithm(
    pop_size=30,
    chromosome_length=chromosome_length,
    generations=40,
    mutation_rate=0.03,
    crossover_rate=0.8,
)

print("\nBest Chromosome:", best_chromosome)
print("Best Fitness Score:", best_score)

selected_features = [
    feature_names[i] for i, gene in enumerate(best_chromosome) if gene == 1
]

print("\nSelected Features:")
print(selected_features)
