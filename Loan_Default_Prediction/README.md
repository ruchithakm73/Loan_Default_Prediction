# Loan Default Prediction

## Project Overview

This is a simple web application to predict loan default risk using a machine learning model. The app provides a web UI for users to register, log in, submit loan applicant data, and receive a default-risk prediction. The repository includes a training script, the dataset, and the Flask web app.

## Features

- Web interface for submitting loan applicant data and viewing predictions.
- Model training script to preprocess data and train a scikit-learn model.
- Simple user registration and authentication flow (templates provided).
- CSV dataset included for reproducible training and evaluation.

## Repository Structure

- `app.py` — Flask application entrypoint serving the web UI and prediction endpoints.
- `model/loan_dataset.csv` — Dataset used to train the model.
- `model/train_model.py` — Script to preprocess data, train and persist the ML model.
- `templates/` — HTML templates (index, register, predict, result, dashboard, etc.).
- `static/` — Static assets (CSS and JavaScript).

## Installation

1. Create and activate a Python virtual environment (recommended):

```bash
python -m venv venv
venv\Scripts\activate    # Windows
```

2. Install required packages. Typical dependencies include `flask`, `pandas`, `scikit-learn`, `numpy`, and `joblib`.

```bash
pip install flask pandas scikit-learn numpy joblib
```

3. (Optional) Create a `requirements.txt` for reproducible installs:

```bash
pip freeze > requirements.txt
```

## Usage

1. Train the model (optional if a trained model file already exists):

```bash
python model/train_model.py
```

This script reads `model/loan_dataset.csv`, performs preprocessing, trains a scikit-learn model, and saves the trained model to the `model/` directory.

2. Run the web app:

```bash
python app.py
```

3. Open a browser and visit `http://127.0.0.1:5000/` to access the app. Use the Register/Login pages to create an account (if enabled), then go to the Predict page to submit applicant data and view results.

## Model & Dataset Notes

- The training script uses scikit-learn. The trained model artifact is saved to the `model/` folder (check `train_model.py` for exact filename and format).
- The dataset `model/loan_dataset.csv` contains the raw data used for training. Review the CSV columns to see which features are used for prediction and how missing values or categorical variables are handled.
- If you modify preprocessing or model hyperparameters, re-run `model/train_model.py` and update the model artifact used by the web app.

## Troubleshooting

- If the app errors on model loading, ensure the trained model file exists in `model/` and matches the loading code in `app.py`.
- If missing dependencies cause import errors, install them with `pip install` as shown above.

## Contributing

Contributions are welcome. Suggested next steps:

- Add a `requirements.txt` capturing exact versions.
- Add unit tests for the preprocessing and prediction logic.
- Add a Dockerfile for containerized deployment.

## License

Specify a license for the project (e.g., MIT) by adding a `LICENSE` file.

## Contact

If you need help or want to propose changes, open an issue or pull request on the repository.
