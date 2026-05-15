import pandas as pd
import joblib
import numpy as np

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

# Load dataset
df = pd.read_csv("loan_dataset.csv")

# Handle missing values
df.ffill(inplace=True)

print("Dataset shape:", df.shape)
print("Target distribution:")
print(df['loan_paid_back'].value_counts(normalize=True))

feature_columns = [
    'gender',
    'age',
    'annual_income',
    'loan_amount',
    'credit_score',
    'num_of_delinquencies'
]

target_column = 'loan_paid_back'

X = df[feature_columns]
y = df[target_column]

categorical_features = ['gender']

preprocessor = ColumnTransformer(
    transformers=[
        ('gender_encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
    ],
    remainder='passthrough'
)

# Use SMOTE for oversampling minority class and better class weights
model_pipeline = ImbPipeline(
    steps=[
        ('preprocessor', preprocessor),
        ('smote', SMOTE(random_state=42, sampling_strategy='auto')),
        ('classifier', RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            class_weight='balanced_subsample',  # Better than 'balanced'
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            bootstrap=True
        ))
    ]
)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y  # Stratify to maintain class distribution
)

model_pipeline.fit(X_train, y_train)

predictions = model_pipeline.predict(X_test)
accuracy = accuracy_score(y_test, predictions)
print(f"Model Accuracy: {accuracy:.4f}")
print("\nClassification Report:")
print(classification_report(y_test, predictions, target_names=['High Risk', 'Low Risk']))
print("\nConfusion Matrix:")
print(confusion_matrix(y_test, predictions))

joblib.dump(model_pipeline, "../model.pkl")
print("Model trained and saved successfully!")
