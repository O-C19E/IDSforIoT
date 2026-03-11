import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import classification_report
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

label_encoder = LabelEncoder()
df["label"] = label_encoder.fit_transform(df["label"].astype(str))

X = df.drop(columns=["label"])
y = df["label"]

X = X.values
y = y.values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42
)

model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=6,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
)

model.fit(X_train, y_train)

preds = model.predict(X_test)
print(classification_report(y_test, preds))
model.save_model("xgb_model.json")

print("Model saved as xgb_model.json")
