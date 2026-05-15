from io import BytesIO
from datetime import datetime
import sqlite3
import os

from flask import Flask, render_template, request, send_file, session, redirect, url_for, flash

import joblib
import numpy as np
import pandas as pd
from werkzeug.utils import secure_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a random secret key

# Load model
model = joblib.load("model.pkl")

# Database setup
DATABASE = 'users.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            gender TEXT NOT NULL,
            age INTEGER NOT NULL,
            annual_income REAL NOT NULL,
            loan_amount REAL NOT NULL,
            credit_score REAL NOT NULL,
            num_of_delinquencies REAL NOT NULL,
            result TEXT NOT NULL,
            probability REAL NOT NULL,
            pdf_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        db.commit()

init_db()

@app.route('/')
def home():
    if 'user_id' in session:
        return render_template('index.html')
    else:
        return render_template('welcome.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    # Accept a fixed admin credential
    if username.strip().lower() == 'admin@loanpredict.com' and password == 'admin123':
        session['is_admin'] = True
        session['username'] = username
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
    db.close()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect(url_for('home'))
    else:
        flash('Invalid username or password')
        return redirect(url_for('home'))

@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = request.form['password']
    confirm_password = request.form.get('confirm_password', '')
    
    if password != confirm_password:
        flash('Passwords do not match.')
        return redirect(url_for('register_page'))
    
    if len(password) < 6:
        flash('Password must be at least 6 characters long.')
        return redirect(url_for('register_page'))
    
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        db.commit()
        flash('Registration successful! Please login with your credentials.')
    except sqlite3.IntegrityError:
        flash('Username already exists. Please choose a different username.')
    db.close()
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    return redirect(url_for('home'))

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash('New passwords do not match.')
            return redirect(url_for('change_password'))
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters long.')
            return redirect(url_for('change_password'))
        
        db = get_db()
        # Verify current password
        user = db.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if not user or user['password'] != current_password:
            flash('Current password is incorrect.')
            db.close()
            return redirect(url_for('change_password'))
        
        # Update password
        db.execute('UPDATE users SET password = ? WHERE id = ?', (new_password, session['user_id']))
        db.commit()
        db.close()
        
        flash('Password updated successfully!')
        return redirect(url_for('home'))
    
    return render_template('change_password.html')

@app.route('/predict')
def predict():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    return render_template('predict.html', error=None, form_data=None)


@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    db = get_db()
    total_users = db.execute('SELECT COUNT(*) AS cnt FROM users').fetchone()['cnt']
    total_apps = db.execute('SELECT COUNT(*) AS cnt FROM predictions').fetchone()['cnt']

    # Determine which columns exist to avoid SQL errors on older DBs
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]

    # Ensure `status` and `pdf_path` columns exist and set automatic statuses based on risk level
    if 'status' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN status TEXT")
            db.commit()
            cols.append('status')
        except Exception:
            pass
    if 'pdf_path' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN pdf_path TEXT")
            db.commit()
            cols.append('pdf_path')
        except Exception:
            pass

    # Auto-set status based on `result` for rows without a decision (NULL/empty/'Pending')
    try:
        db.execute("UPDATE predictions SET status = 'Approved' WHERE (status IS NULL OR status = '' OR status = 'Pending') AND result = 'Low Risk'")
        db.execute("UPDATE predictions SET status = 'Rejected' WHERE (status IS NULL OR status = '' OR status = 'Pending') AND result = 'High Risk'")
        db.execute("UPDATE predictions SET status = 'Pending' WHERE (status IS NULL OR status = '') AND (result = 'Medium Risk' OR result = 'Medium')")
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # Approved loans: prefer explicit 'status' = 'Approved' if available, otherwise use result = 'Low Risk'
    if 'status' in cols:
        approved_loans = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE status = 'Approved'").fetchone()['cnt']
    else:
        approved_loans = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'Low Risk'").fetchone()['cnt']

    # Risk counts: use risk_percentage bands if available, otherwise fall back to result
    if 'risk_percentage' in cols:
        # Include fallback to `result` in case `risk_percentage` is NULL for older rows
        # Use bands: 100-300 => High, 301-600 => Medium, 601-900 => Low
        high_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 100 AND 300) OR result = 'High Risk'").fetchone()['cnt']
        medium_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 301 AND 600) OR result = 'Medium Risk'").fetchone()['cnt']
        low_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 601 AND 900) OR result = 'Low Risk'").fetchone()['cnt']
    else:
        high_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'High Risk'").fetchone()['cnt']
        medium_risk = 0
        low_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'Low Risk'").fetchone()['cnt']

    # Fetch recent applications to display in the admin table
    # Select common columns and include status if available
    select_cols = ['id', 'name', 'result', 'probability', 'created_at']
    if 'risk_percentage' in cols:
        select_cols.append('risk_percentage')
    if 'status' in cols:
        select_cols.append('status')
    if 'pdf_path' in cols:
        select_cols.append('pdf_path')
    sql = 'SELECT ' + ','.join(select_cols) + ' FROM predictions ORDER BY created_at DESC'
    applications = db.execute(sql).fetchall()
    db.close()

    return render_template('admin_dashboard.html',
                           total_users=total_users,
                           total_apps=total_apps,
                           approved_loans=approved_loans,
                           high_risk=high_risk,
                           medium_risk=medium_risk,
                           low_risk=low_risk,
                           applications=applications,
                           username=session.get('username', 'Admin'))


@app.route('/admin/approve/<int:pred_id>', methods=['POST'])
def admin_approve(pred_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    db = get_db()
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]
    if 'status' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN status TEXT")
            db.commit()
        except Exception:
            pass
    db.execute("UPDATE predictions SET status = 'Approved' WHERE id = ?", (pred_id,))
    db.commit()
    db.close()
    flash('Application approved')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/reject/<int:pred_id>', methods=['POST'])
def admin_reject(pred_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    db = get_db()
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]
    if 'status' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN status TEXT")
            db.commit()
        except Exception:
            pass
    db.execute("UPDATE predictions SET status = 'Rejected' WHERE id = ?", (pred_id,))
    db.commit()
    db.close()
    flash('Application rejected')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/<int:pred_id>', methods=['POST'])
def admin_delete(pred_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))
    db = get_db()
    try:
        db.execute('DELETE FROM predictions WHERE id = ?', (pred_id,))
        db.commit()
        flash('Application removed')
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        flash('Could not remove application', 'danger')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/get_predictions')
def get_predictions():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    db = get_db()
    predictions = db.execute('SELECT * FROM predictions WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    db.close()
    return predictions

@app.route('/delete_prediction/<int:pred_id>', methods=['POST'])
def delete_prediction(pred_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    db = get_db()
    db.execute('DELETE FROM predictions WHERE id = ? AND user_id = ?', (pred_id, session['user_id']))
    db.commit()
    db.close()
    flash('Prediction deleted successfully')
    return redirect(url_for('dashboard'))


@app.route('/edit_prediction/<int:pred_id>')
def edit_prediction(pred_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    db = get_db()
    pred = db.execute('SELECT * FROM predictions WHERE id = ? AND user_id = ?', (pred_id, session['user_id'])).fetchone()
    db.close()
    if not pred:
        flash('Prediction not found')
        return redirect(url_for('dashboard'))
    return render_template('edit_prediction.html', pred=pred)


@app.route('/update_prediction/<int:pred_id>', methods=['POST'])
def update_prediction(pred_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))

    # Read submitted form values
    name = request.form.get('name', '').strip()
    gender = request.form.get('gender', '')
    try:
        age = int(request.form.get('age', 0))
    except ValueError:
        flash('Invalid age')
        return redirect(url_for('edit_prediction', pred_id=pred_id))

    try:
        income = float(request.form.get('annual_income', 0))
    except ValueError:
        income = 0.0
    try:
        loan = float(request.form.get('loan_amount', 0))
    except ValueError:
        loan = 0.0
    try:
        credit = float(request.form.get('credit_score', 0))
    except ValueError:
        credit = 0.0

    employment_status = request.form.get('employment_status', '')

    # Recompute prediction using the same logic as /submit
    input_df = pd.DataFrame([{
        'gender': gender,
        'age': age,
        'annual_income': income,
        'loan_amount': loan,
        'credit_score': credit,
        'num_of_delinquencies': 0.0
    }])

    try:
        prediction = model.predict(input_df)[0]
        probability = model.predict_proba(input_df)[0][1] * 100
        probability = round(probability, 2)
    except Exception:
        # If model fails, keep a fallback
        prediction = 1
        probability = 0.0

    # Risk scoring (same rules as submit)
    risk_score = 0
    if age < 25:
        risk_score += 2
    elif age < 35:
        risk_score += 1

    income_to_loan_ratio = income / loan if loan > 0 else 0
    if income_to_loan_ratio < 0.5:
        risk_score += 3
    elif income_to_loan_ratio < 1:
        risk_score += 2
    elif income_to_loan_ratio < 2:
        risk_score += 1

    if credit < 400:
        risk_score += 3
    elif credit < 600:
        risk_score += 2
    elif credit < 700:
        risk_score += 1

    delinquency = 0.0
    if delinquency > 3:
        risk_score += 3
    elif delinquency > 1:
        risk_score += 2
    elif delinquency > 0:
        risk_score += 1

    if employment_status and employment_status.strip().lower() == 'unemployed':
        result = "High Risk"
        prediction = 0
        probability = max(10, min(probability, 30))
    else:
        if risk_score >= 5 or probability < 65:
            result = "High Risk"
            prediction = 0
            probability = max(10, probability - 20)
        else:
            result = "Low Risk"
            prediction = 1

    raw_score = int(probability * 6 + max(0, 10 - risk_score) * 10) + 100
    risk_percentage = max(100, min(900, raw_score))
    if employment_status and employment_status.strip().lower() == 'unemployed':
        risk_percentage = max(100, min(300, risk_percentage, 200))

    # Classify by credit score bands per updated policy:
    # 300-649 -> High Risk, 650-749 -> Medium Risk, 750-900 -> Low Risk
    try:
        cscore = int(credit)
    except Exception:
        cscore = None

    if cscore is not None and 300 <= cscore <= 649:
        risk_level = 'High Risk'
        risk_class = 'high'
        # representative risk_percentage in high-risk band
        risk_percentage = 200
        result = 'High Risk'
        prediction = 0
    elif cscore is not None and 650 <= cscore <= 749:
        risk_level = 'Medium Risk'
        risk_class = 'medium'
        risk_percentage = 450
        result = 'Medium Risk'
        prediction = 0
    elif cscore is not None and 750 <= cscore <= 900:
        risk_level = 'Low Risk'
        risk_class = 'low'
        risk_percentage = 750
        result = 'Low Risk'
        prediction = 1
    else:
        # Fallback for missing/invalid scores: treat as Low Risk
        risk_level = 'Low Risk'
        risk_class = 'low'
        risk_percentage = 750
        result = 'Low Risk'
        prediction = 1

    # Unemployed should always be treated as High Risk regardless of credit band
    if employment_status and employment_status.strip().lower() == 'unemployed':
        risk_level = 'High Risk'
        risk_class = 'high'
        risk_percentage = 200
        result = 'High Risk'
        prediction = 0

    # Map to status
    if risk_level == 'Low Risk':
        status = 'Approved'
    elif risk_level == 'High Risk':
        status = 'Rejected'
    else:
        status = 'Pending'

    # Persist updates
    db = get_db()
    db.execute('''UPDATE predictions SET name = ?, gender = ?, age = ?, annual_income = ?, loan_amount = ?, credit_score = ?, result = ?, probability = ?, risk_percentage = ?, status = ? WHERE id = ? AND user_id = ?''',
               (name, gender, age, income, loan, credit, result, probability, risk_percentage, status, pred_id, session['user_id']))
    db.commit()
    db.close()

    flash('Prediction updated successfully')
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    
    db = get_db()
    predictions = db.execute('SELECT * FROM predictions WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()

    # Compute global statistics so dashboard matches admin totals
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]
    total = db.execute("SELECT COUNT(*) AS cnt FROM predictions").fetchone()['cnt']
    if 'risk_percentage' in cols:
        high_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 100 AND 300) OR result = 'High Risk'").fetchone()['cnt']
        medium_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 301 AND 600) OR result = 'Medium Risk'").fetchone()['cnt']
        low_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE (risk_percentage BETWEEN 601 AND 900) OR result = 'Low Risk'").fetchone()['cnt']
    else:
        high_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'High Risk'").fetchone()['cnt']
        medium_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'Medium Risk' OR result = 'Medium'").fetchone()['cnt']
        low_risk = db.execute("SELECT COUNT(*) AS cnt FROM predictions WHERE result = 'Low Risk'").fetchone()['cnt']

    avg_row = db.execute("SELECT AVG(probability) AS avgp FROM predictions").fetchone()
    avg_probability = round(avg_row['avgp'], 2) if avg_row and avg_row['avgp'] is not None else 0
    db.close()
    
    return render_template(
        'dashboard.html',
        predictions=predictions,
        total=total,
        high_risk=high_risk,
        medium_risk=medium_risk,
        low_risk=low_risk,
        avg_probability=avg_probability,
        username=session.get('username', 'User')
    )

@app.route('/submit', methods=['POST'])
def submit():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    # Get form data
    name = request.form['name'].strip()
    gender = request.form['gender']
    try:
        age = int(request.form['age'])
    except ValueError:
        return render_template(
            'predict.html',
            error='Age must be a positive integer.',
            form_data={
                'name': name,
                'gender': gender,
                'age': request.form['age'],
                'annual_income': request.form['annual_income'],
                'loan_amount': request.form['loan_amount'],
                'credit_score': request.form['credit_score'],
                'employment_status': request.form.get('employment_status', '')
            }
        )
    if age < 18:
        return render_template(
            'predict.html',
            error='Age must be greater than or equal to 18.',
            form_data={
                'name': name,
                'gender': gender,
                'age': age,
                'annual_income': float(request.form['annual_income']) if request.form['annual_income'] else 0,
                'loan_amount': float(request.form['loan_amount']) if request.form['loan_amount'] else 0,
                'credit_score': float(request.form['credit_score']) if request.form['credit_score'] else 0,
                'employment_status': request.form.get('employment_status', '')
            }
        )
    income = float(request.form['annual_income'])
    loan = float(request.form['loan_amount'])
    credit = float(request.form['credit_score'])
    # Employment status is collected from the form; the model expects
    # `num_of_delinquencies` numeric feature, so we default it to 0 here
    # while preserving the employment status for reporting.
    employment_status = request.form.get('employment_status', '')
    delinquency = 0.0

    # Convert to model input
    input_df = pd.DataFrame([{
        'gender': gender,
        'age': age,
        'annual_income': income,
        'loan_amount': loan,
        'credit_score': credit,
        'num_of_delinquencies': delinquency
    }])

    # Predict class and repayment probability
    prediction = model.predict(input_df)[0]
    probability = model.predict_proba(input_df)[0][1] * 100
    probability = round(probability, 2)

    # Rule-based risk assessment for better high-risk detection
    risk_score = 0

    # Age factor (younger applicants are higher risk)
    if age < 25:
        risk_score += 2
    elif age < 35:
        risk_score += 1

    # Income to loan ratio (higher ratio = higher risk)
    income_to_loan_ratio = income / loan if loan > 0 else 0
    if income_to_loan_ratio < 0.5:
        risk_score += 3
    elif income_to_loan_ratio < 1:
        risk_score += 2
    elif income_to_loan_ratio < 2:
        risk_score += 1

    # Credit score factor
    if credit < 400:
        risk_score += 3
    elif credit < 600:
        risk_score += 2
    elif credit < 700:
        risk_score += 1

    # Delinquencies factor
    if delinquency > 3:
        risk_score += 3
    elif delinquency > 1:
        risk_score += 2
    elif delinquency > 0:
        risk_score += 1

    # Final decision based on risk score and ML probability
    # If employment status explicitly indicates 'Unemployed', classify as High Risk
    if employment_status and employment_status.strip().lower() == 'unemployed':
        result = "High Risk"
        prediction = 0
        # Lower the reported probability for unemployed applicants
        probability = max(10, min(probability, 30))
    else:
        if risk_score >= 5 or probability < 65:
            result = "High Risk"
            prediction = 0
            # Adjust probability to reflect higher risk
            probability = max(10, probability - 20)
        else:
            result = "Low Risk"
            prediction = 1

    # Compute a risk percentage on a 100-900 scale where higher = safer (lower credit risk)
    raw_score = int(probability * 6 + max(0, 10 - risk_score) * 10) + 100
    risk_percentage = max(100, min(900, raw_score))

    # If applicant is unemployed, force a low risk_percentage (i.e., high risk)
    if employment_status and employment_status.strip().lower() == 'unemployed':
        risk_percentage = max(100, min(300, risk_percentage, 200))

    # Classify by credit score bands per user request (credit 100-300 -> High, 301-600 -> Medium, 601-900 -> Low)
    try:
        cscore = int(credit)
    except Exception:
        cscore = None

    if cscore is not None and 300 <= cscore <= 649:
        risk_level = 'High Risk'
        risk_class = 'high'
        risk_percentage = 200
        result = 'High Risk'
        prediction = 0
    elif cscore is not None and 650 <= cscore <= 749:
        risk_level = 'Medium Risk'
        risk_class = 'medium'
        risk_percentage = 450
        result = 'Medium Risk'
        prediction = 0
    elif cscore is not None and 750 <= cscore <= 900:
        risk_level = 'Low Risk'
        risk_class = 'low'
        risk_percentage = 750
        result = 'Low Risk'
        prediction = 1
    else:
        risk_level = 'Low Risk'
        risk_class = 'low'
        risk_percentage = 750
        result = 'Low Risk'
        prediction = 1

    # Unemployed should always be treated as High Risk regardless of credit band
    if employment_status and employment_status.strip().lower() == 'unemployed':
        risk_level = 'High Risk'
        risk_class = 'high'
        risk_percentage = 200
        result = 'High Risk'
        prediction = 0

    # Map to status
    if risk_level == 'Low Risk':
        status = 'Approved'
    elif risk_level == 'High Risk':
        status = 'Rejected'
    else:
        status = 'Pending'

    # Round probability for display and storage
    try:
        probability = round(float(probability), 2)
    except Exception:
        pass

    # Ensure `status` column exists
    db = get_db()
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]
    if 'status' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN status TEXT")
            db.commit()
        except Exception:
            pass

    # Store prediction in database (include risk_percentage and status)
    db.execute('''INSERT INTO predictions 
                  (user_id, name, gender, age, annual_income, loan_amount, credit_score, num_of_delinquencies, result, probability, risk_percentage, status)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
               (session['user_id'], name, gender, age, income, loan, credit, delinquency, result, probability, risk_percentage, status))
    db.commit()
    db.close()

    return render_template(
        'result.html',
        name=name,
        gender=gender,
        result=result,
        probability=probability,
        age=age,
        income=income,
        loan=loan,
        credit=credit,
        delinquency=delinquency,
        employment_status=employment_status,
        risk_percentage=risk_percentage,
        risk_level=risk_level,
        risk_class=risk_class
    )

@app.route('/download_report', methods=['POST'])
def download_report():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    name = request.form.get('name', 'Applicant')
    gender = request.form.get('gender', 'Not specified')
    age = float(request.form['age'])
    income = float(request.form['annual_income'])
    loan = float(request.form['loan_amount'])
    credit = float(request.form['credit_score'])
    employment_status = request.form.get('employment_status', 'Not provided')
    result = request.form['result']
    probability = float(request.form['probability'])

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Header', fontSize=20, leading=24, spaceAfter=20, alignment=1, textColor=colors.HexColor('#0b3861')))
    styles.add(ParagraphStyle(name='Subheader', fontSize=11, leading=14, spaceAfter=12, textColor=colors.grey))
    styles.add(ParagraphStyle(name='Body', fontSize=11, leading=15, spaceAfter=12))
    styles.add(ParagraphStyle(name='RiskLabel', fontSize=12, leading=16, spaceAfter=14, textColor=colors.white, alignment=1, borderPadding=8))

    elements = []
    elements.append(Paragraph('Loan Repayment Risk Report', styles['Header']))
    elements.append(Paragraph(f'Report generated on: {datetime.now():%B %d, %Y %H:%M}', styles['Subheader']))

    details = [
        ['Applicant Detail', 'Value'],
        ['Name', name],
        ['Gender', gender],
        ['Age', f'{age:.0f}'],
        ['Annual Income', f'₹{income:,.2f}'],
        ['Loan Amount', f'₹{loan:,.2f}'],
        ['Credit Score', f'{credit:.0f}'],
        ['Employment Status', employment_status],
    ]
    table = Table(details, hAlign='LEFT', colWidths=[220, 220])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b3861')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f2f4f8')),
        ('BOX', (0, 0), (-1, -1), 1, colors.grey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))

    risk_color = colors.HexColor('#d9534f') if result == 'High Risk' else colors.HexColor('#28a745')
    risk_style = ParagraphStyle(name='RiskLabel', fontSize=12, leading=16, spaceAfter=12, textColor=colors.white, backColor=risk_color, alignment=1, borderPadding=8)
    elements.append(Paragraph(f'Prediction Outcome: {result}', risk_style))
    elements.append(Paragraph(f'Repayment Probability: <b>{probability:.2f}%</b>', styles['Body']))

    recommendation = (
        'This borrower is likely to repay the loan on time. Continue with approval and monitor portfolio exposure.'
        if result == 'Low Risk'
        else 'This borrower presents elevated risk. Consider additional collateral, tighter terms, or a co-signer before approving.'
    )
    elements.append(Paragraph('<b>Recommendation</b>', styles['Body']))
    elements.append(Paragraph(recommendation, styles['Body']))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph('Disclaimer: This report is based on a machine learning model and should be used as one input in your overall credit decision process.', styles['Subheader']))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='loan_prediction_report.pdf',
        mimetype='application/pdf'
    )


@app.route('/select_loan', methods=['POST'])
def select_loan():
    if 'user_id' not in session:
        return redirect(url_for('home'))
    loan_category = request.form.get('loan_category')
    if not loan_category:
        flash('Please select a loan category.')
        return redirect(url_for('dashboard'))
    return render_template('loan_selection.html', loan_category=loan_category, username=session.get('username', 'User'))


@app.route('/loan_selection_for/<int:pred_id>')
def loan_selection_for(pred_id):
    if 'user_id' not in session:
        return redirect(url_for('home'))
    db = get_db()
    pred = db.execute('SELECT * FROM predictions WHERE id = ? AND user_id = ?', (pred_id, session['user_id'])).fetchone()
    db.close()
    if not pred:
        flash('Prediction not found')
        return redirect(url_for('dashboard'))
    # Default to Personal Loan; user can change on the loan selection page
    loan_category = 'Personal Loan'
    return render_template('loan_selection.html', loan_category=loan_category, pred=pred, username=session.get('username', 'User'))


@app.route('/apply/personal', methods=['GET', 'POST'])
def apply_personal():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'GET':
        return render_template('personal_application.html')

    # POST: handle form submission
    # Read fields that match the new detailed form
    applicant_name = request.form.get('full_name') or request.form.get('applicant_name')
    dob_str = request.form.get('dob')
    applicant_mobile = request.form.get('mobile') or request.form.get('applicant_mobile')
    applicant_email = request.form.get('email') or request.form.get('applicant_email')
    address = request.form.get('address')
    aadhaar = request.form.get('aadhaar')
    pan = request.form.get('pan')
    bank_name = request.form.get('bank_name')
    account_number = request.form.get('account_number') or request.form.get('bank_account')
    ifsc = request.form.get('ifsc')

    # Parse DOB and validate age between 18 and 60
    try:
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
    except Exception:
        dob = None

    if not dob:
        flash('Please provide a valid Date of Birth.', 'danger')
        return render_template('personal_application.html')

    today = datetime.today().date()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18 or age > 60:
        flash('Applicants must be between 18 and 60 years of age to apply for a loan.', 'danger')
        return render_template('personal_application.html')

    # Save uploaded documents to organized folders
    uploads_base = os.path.join('static', 'uploads', 'personal')
    os.makedirs(uploads_base, exist_ok=True)

    def save_file(field_name, subfolder):
        f = request.files.get(field_name)
        if f and f.filename:
            folder = os.path.join(uploads_base, subfolder)
            os.makedirs(folder, exist_ok=True)
            filename = secure_filename(f.filename)
            path = os.path.join(folder, filename)
            f.save(path)
            return path
        return None

    saved = {}
    saved['aadhaar_card'] = save_file('aadhaar_file', 'aadhaar')
    saved['pan_card'] = save_file('pan_file', 'pan')
    saved['photo'] = save_file('photo', 'photo')
    saved['address_proof'] = save_file('address_proof', 'address_proof')

    # TODO: persist application details to DB or trigger workflow
    flash('Personal Loan application submitted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/apply/home', methods=['GET', 'POST'])
def apply_home():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'GET':
        return render_template('home_application.html')

    # POST: process home loan application
    full_name = request.form.get('full_name')
    dob = request.form.get('dob')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    address = request.form.get('address')
    aadhaar = request.form.get('aadhaar')
    pan = request.form.get('pan')
    bank_account = request.form.get('bank_account')
    house_location = request.form.get('house_location')
    property_value = request.form.get('property_value')
    property_type = request.form.get('property_type')

    # Handle uploads
    uploads_base = os.path.join('static', 'uploads', 'home')
    os.makedirs(uploads_base, exist_ok=True)

    def save_file(field_name, subfolder):
        f = request.files.get(field_name)
        if f and f.filename:
            folder = os.path.join(uploads_base, subfolder)
            os.makedirs(folder, exist_ok=True)
            filename = secure_filename(f.filename)
            path = os.path.join(folder, filename)
            f.save(path)
            return path
        return None

    address_proof_path = save_file('address_proof', 'address_proof')
    property_docs_path = save_file('property_docs', 'property_docs')
    photo_path = save_file('photo', 'photo')
    signature_path = save_file('signature', 'signature')

    # TODO: persist application to DB or further processing
    flash('Home Loan application submitted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/apply/education', methods=['GET', 'POST'])
def apply_education():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'GET':
        return render_template('education_application.html')

    # POST: collect form fields
    student_name = request.form.get('student_name')
    dob = request.form.get('dob')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    address = request.form.get('address')

    college_name = request.form.get('college_name')
    course_name = request.form.get('course_name')
    course_duration = request.form.get('course_duration')
    semester = request.form.get('semester')

    parent_name = request.form.get('parent_name')
    parent_occupation = request.form.get('parent_occupation')
    parent_income = request.form.get('parent_income')
    parent_mobile = request.form.get('parent_mobile')

    loan_amount_needed = request.form.get('loan_amount_needed')
    loan_purpose = request.form.get('loan_purpose')
    repayment_period = request.form.get('repayment_period')

    bank_name = request.form.get('bank_name')
    account_number = request.form.get('account_number')
    ifsc = request.form.get('ifsc')

    # Save uploaded documents
    uploads_base = os.path.join('static', 'uploads', 'education')
    os.makedirs(uploads_base, exist_ok=True)

    def save_file(field_name, subfolder):
        f = request.files.get(field_name)
        if f and f.filename:
            folder = os.path.join(uploads_base, subfolder)
            os.makedirs(folder, exist_ok=True)
            filename = secure_filename(f.filename)
            path = os.path.join(folder, filename)
            f.save(path)
            return path
        return None

    saved = {}
    saved['aadhaar_card'] = save_file('aadhaar_card', 'aadhaar')
    saved['pan_card'] = save_file('pan_card', 'pan')
    saved['photo'] = save_file('photo', 'photo')
    saved['fee_structure'] = save_file('fee_structure', 'fee_structure')
    saved['marks_cards'] = save_file('marks_cards', 'marks_cards')
    saved['income_proof'] = save_file('income_proof', 'income_proof')
    saved['bank_statement'] = save_file('bank_statement', 'bank_statement')
    saved['address_proof'] = save_file('address_proof', 'address_proof')

    # Generate a PDF summary of the application and save it
    pdf_folder = os.path.join('static', 'uploads', 'education', 'pdfs')
    os.makedirs(pdf_folder, exist_ok=True)
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    safe_name = secure_filename((student_name or 'application').replace(' ', '_'))
    pdf_filename = f"{safe_name}_{timestamp}.pdf"
    pdf_path = os.path.join(pdf_folder, pdf_filename)

    # Build PDF content
    def generate_pdf(path, data, saved_files):
        doc = SimpleDocTemplate(path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph('Education Loan Application', styles['Title']))
        story.append(Spacer(1, 12))

        # Applicant details table
        rows = []
        rows.append(['Field', 'Value'])
        rows.append(['Student Name', data.get('student_name', '')])
        rows.append(['DOB', data.get('dob', '')])
        rows.append(['Mobile', data.get('mobile', '')])
        rows.append(['Email', data.get('email', '')])
        rows.append(['Address', data.get('address', '')])
        rows.append(['College', data.get('college_name', '')])
        rows.append(['Course', data.get('course_name', '')])
        rows.append(['Course Duration', data.get('course_duration', '')])
        rows.append(['Semester', data.get('semester', '')])
        rows.append(['Parent Name', data.get('parent_name', '')])
        rows.append(['Parent Occupation', data.get('parent_occupation', '')])
        rows.append(['Parent Income', data.get('parent_income', '')])
        rows.append(['Loan Amount Needed', data.get('loan_amount_needed', '')])
        rows.append(['Loan Purpose', data.get('loan_purpose', '')])
        rows.append(['Repayment Period', data.get('repayment_period', '')])
        rows.append(['Bank Name', data.get('bank_name', '')])
        rows.append(['Account Number', data.get('account_number', '')])
        rows.append(['IFSC', data.get('ifsc', '')])

        t = Table(rows, colWidths=[150, 350])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

        # Add uploaded filenames
        story.append(Paragraph('Uploaded Documents', styles['Heading3']))
        for k, v in saved_files.items():
            story.append(Paragraph(f"{k}: {os.path.basename(v) if v else 'Not provided'}", styles['Normal']))

        doc.build(story)

    try:
        generate_pdf(pdf_path, {
            'student_name': student_name,
            'dob': dob,
            'mobile': mobile,
            'email': email,
            'address': address,
            'college_name': college_name,
            'course_name': course_name,
            'course_duration': course_duration,
            'semester': semester,
            'parent_name': parent_name,
            'parent_occupation': parent_occupation,
            'parent_income': parent_income,
            'loan_amount_needed': loan_amount_needed,
            'loan_purpose': loan_purpose,
            'repayment_period': repayment_period,
            'bank_name': bank_name,
            'account_number': account_number,
            'ifsc': ifsc
        }, saved)
    except Exception:
        pdf_path = None

    # Persist a lightweight record in predictions so admin dashboard shows the application
    db = get_db()
    cols = [r[1] for r in db.execute("PRAGMA table_info(predictions)").fetchall()]
    if 'pdf_path' not in cols:
        try:
            db.execute("ALTER TABLE predictions ADD COLUMN pdf_path TEXT")
            db.commit()
            cols.append('pdf_path')
        except Exception:
            pass

    try:
        db.execute('''INSERT INTO predictions (user_id, name, gender, age, annual_income, loan_amount, credit_score, num_of_delinquencies, result, probability, pdf_path)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                   (session['user_id'], student_name or 'Applicant', 'N/A', 0, 0.0, float(loan_amount_needed or 0), 0.0, 0.0, 'Application', 0.0, (pdf_path.replace('static\\', '') if pdf_path else None)))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    db.close()

    # If PDF generated, return it inline so browser opens it directly
    if pdf_path and os.path.exists(pdf_path):
        try:
            resp = send_file(pdf_path, mimetype='application/pdf', as_attachment=False)
            # Force inline content-disposition so browsers open in-view
            resp.headers['Content-Disposition'] = f'inline; filename="{pdf_filename}"'
            return resp
        except Exception:
            # If sending fails, fall back to dashboard
            flash('Application submitted but PDF could not be opened. You can view it from Admin.', 'warning')
            return redirect(url_for('dashboard'))

    flash('Education Loan application submitted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/apply/vehicle', methods=['GET', 'POST'])
def apply_vehicle():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'GET':
        return render_template('vehicle_application.html')

    # POST: gather fields
    full_name = request.form.get('full_name')
    dob = request.form.get('dob')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    address = request.form.get('address')
    bank_account = request.form.get('bank_account')

    aadhaar = request.form.get('aadhaar')
    pan = request.form.get('pan')
    driving_license_num = request.form.get('driving_license')

    vehicle_type = request.form.get('vehicle_type')
    brand_model = request.form.get('brand_model')
    vehicle_price = request.form.get('vehicle_price')
    vehicle_condition = request.form.get('vehicle_condition')

    uploads_base = os.path.join('static', 'uploads', 'vehicle')
    os.makedirs(uploads_base, exist_ok=True)

    def save_file(field_name, subfolder):
        f = request.files.get(field_name)
        if f and f.filename:
            folder = os.path.join(uploads_base, subfolder)
            os.makedirs(folder, exist_ok=True)
            filename = secure_filename(f.filename)
            path = os.path.join(folder, filename)
            f.save(path)
            return path
        return None

    saved = {}
    saved['aadhaar_card'] = save_file('aadhaar_card', 'aadhaar')
    saved['pan_card'] = save_file('pan_card', 'pan')
    saved['photo'] = save_file('photo', 'photo')
    saved['address_proof'] = save_file('address_proof', 'address_proof')
    saved['driving_license_doc'] = save_file('driving_license_doc', 'driving_license')
    saved['vehicle_quotation'] = save_file('vehicle_quotation', 'vehicle_quotation')

    # TODO: persist vehicle loan application
    flash('Vehicle Loan application submitted successfully.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/apply/business', methods=['GET', 'POST'])
def apply_business():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'GET':
        return render_template('business_application.html')

    # POST: collect fields
    full_name = request.form.get('full_name')
    mobile = request.form.get('mobile')
    email = request.form.get('email')
    address = request.form.get('address')
    dob = request.form.get('dob')

    business_name = request.form.get('business_name')
    business_type = request.form.get('business_type')
    business_address = request.form.get('business_address')
    years_in_business = request.form.get('years_in_business')
    gst_number = request.form.get('gst_number')

    monthly_income = request.form.get('monthly_income')
    annual_turnover = request.form.get('annual_turnover')
    profit_details = request.form.get('profit_details')

    loan_amount_needed = request.form.get('loan_amount_needed')
    purpose_of_loan = request.form.get('purpose_of_loan')
    loan_tenure = request.form.get('loan_tenure')

    bank_name = request.form.get('bank_name')
    account_number = request.form.get('account_number')
    ifsc_code = request.form.get('ifsc_code')

    # Save uploaded documents
    uploads_base = os.path.join('static', 'uploads', 'business')
    os.makedirs(uploads_base, exist_ok=True)

    def save_file(field_name, subfolder):
        f = request.files.get(field_name)
        if f and f.filename:
            folder = os.path.join(uploads_base, subfolder)
            os.makedirs(folder, exist_ok=True)
            filename = secure_filename(f.filename)
            path = os.path.join(folder, filename)
            f.save(path)
            return path
        return None

    saved = {}
    saved['aadhaar_card'] = save_file('aadhaar_card', 'aadhaar')
    saved['pan_card'] = save_file('pan_card', 'pan')
    saved['photo'] = save_file('photo', 'photo')
    saved['bank_statement'] = save_file('bank_statement', 'bank_statement')
    saved['gst_certificate'] = save_file('gst_certificate', 'gst_certificate')
    saved['business_license'] = save_file('business_license', 'business_license')
    saved['itr_documents'] = save_file('itr_documents', 'itr_documents')
    saved['address_proof'] = save_file('address_proof', 'address_proof')

    # TODO: persist business loan application to DB or follow workflow
    flash('Business Loan application submitted successfully.', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
