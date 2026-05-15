AOS.init({
    duration: 1000,
    once: true
});

window.addEventListener("scroll", function () {
    const navbar = document.querySelector(".custom-navbar");
    if (window.scrollY > 50) {
        navbar.style.background = "rgba(15, 23, 42, 0.75)";
    } else {
        navbar.style.background = "rgba(255, 255, 255, 0.08)";
    }
});

function showLoader() {
    alert("Processing prediction...");
}

// Validation helpers for application forms
function _calcAgeFromDOB(dobStr) {
    if (!dobStr) return null;
    const dob = new Date(dobStr);
    if (isNaN(dob)) return null;
    const today = new Date();
    let age = today.getFullYear() - dob.getFullYear();
    const m = today.getMonth() - dob.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
        age--;
    }
    return age;
}

function _validateName(name) {
    if (!name) return false;
    // Starts with capital, only letters and spaces
    const re = /^[A-Z][A-Za-z ]+$/;
    return re.test(name.trim());
}

function _validateMobile(mobile) {
    if (!mobile) return false;
    const digits = mobile.replace(/\D/g, '');
    return digits.length === 10;
}

function _validateEmail(email) {
    if (!email) return false;
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email.trim());
}

function _validateAadhaar(aadhaar) {
    if (!aadhaar) return false;
    const digits = aadhaar.replace(/\D/g, '');
    return digits.length === 12;
}

function _validatePAN(pan) {
    if (!pan) return false;
    const re = /^[A-Z]{5}[0-9]{4}[A-Z]$/i;
    return re.test(pan.trim());
}

function _validateIFSC(ifsc) {
    if (!ifsc) return false;
    return ifsc.trim().length === 11;
}

function _validateAccountNumber(acc) {
    if (!acc) return false;
    const digits = acc.replace(/\s+/g, '');
    return /^\d+$/.test(digits);
}

function validateApplicationForm(form) {
    // Clear previous field states
    function _clearFieldState() {
        const stamped = form.querySelectorAll('.input-invalid, .input-valid');
        stamped.forEach(el => {
            el.classList.remove('input-invalid');
            el.classList.remove('input-valid');
        });
        const errs = form.querySelectorAll('.field-error');
        errs.forEach(e => e.textContent = '');
    }
    _clearFieldState();

    // Try common name fields
    const nameFields = ['full_name','applicant_name','student_name','parent_name','guardian_name'];
    const mobileFields = ['mobile','applicant_mobile','parent_mobile','guardian_mobile'];
    const emailFields = ['email','applicant_email'];

    function pickValue(names) {
        for (let n of names) {
            const el = form.querySelector('[name="'+n+'"]');
            if (el && el.value) return {el, value: el.value};
        }
        return {el: null, value: ''};
    }

    const namePick = pickValue(nameFields);
    const dobEl = form.querySelector('[name="dob"]');
    const dob = dobEl ? dobEl.value : '';
    const mobilePick = pickValue(mobileFields);
    const emailPick = pickValue(emailFields);
    // Other common financial fields
    const aadhaarEl = form.querySelector('[name="aadhaar"]') || form.querySelector('[name="aadhaar_card"]') || form.querySelector('[name="aadhaar_file"]');
    const panEl = form.querySelector('[name="pan"]') || form.querySelector('[name="pan_card"]') || form.querySelector('[name="pan_file"]');
    const ifscEl = form.querySelector('[name="ifsc"]') || form.querySelector('[name="ifsc_code"]');
    const accountEl = form.querySelector('[name="account_number"]') || form.querySelector('[name="bank_account"]');

    // Helper to show inline errors / success
    function _showError(el, msg) {
        if (!el) return;
        el.classList.remove('input-valid');
        el.classList.add('input-invalid');
        const parent = el.parentNode;
        let err = parent.querySelector('.field-error');
        if (!err) {
            err = document.createElement('div');
            err.className = 'field-error';
            parent.appendChild(err);
        }
        err.textContent = msg;
    }

    function _showSuccess(el) {
        if (!el) return;
        el.classList.remove('input-invalid');
        el.classList.add('input-valid');
        const parent = el.parentNode;
        const err = parent.querySelector('.field-error');
        if (err) err.textContent = '';
    }

    // Required fields should not be empty (collect all errors, don't alert)
    let allValid = true;
    const requiredEls = form.querySelectorAll('[required]');
    for (let el of requiredEls) {
        if (el.type === 'file') {
            if (!el.files || el.files.length === 0) {
                _showError(el, 'This field is required.');
                allValid = false;
            } else {
                _showSuccess(el);
            }
        } else if (el.type === 'checkbox' || el.type === 'radio') {
            continue;
        } else {
            if (!el.value || !el.value.toString().trim()) {
                _showError(el, 'This field is required.');
                allValid = false;
            } else {
                _showSuccess(el);
            }
        }
    }

    // Age check: only enforce if dob field exists and (required OR has a value)
    if (dobEl && (dobEl.required || dob)) {
        const dobDate = new Date(dob);
        const today = new Date();
        if (isNaN(dobDate.getTime())) {
            _showError(dobEl, 'Please enter a valid Date of Birth.');
            allValid = false;
        } else if (dobDate > today) {
            _showError(dobEl, 'Date of Birth cannot be a future date.');
            allValid = false;
        } else {
            const age = _calcAgeFromDOB(dob);
            if (age === null || isNaN(age)) {
                _showError(dobEl, 'Please enter a valid Date of Birth.');
                allValid = false;
            } else if (age < 18 || age > 60) {
                _showError(dobEl, 'Applicants must be between 18 and 60 years of age.');
                allValid = false;
            } else {
                _showSuccess(dobEl);
            }
        }
    }

    // Name check
    if (namePick.el && (namePick.el.required || namePick.value)) {
        if (!_validateName(namePick.value)) {
            _showError(namePick.el, 'Full name must start with a capital letter and contain only alphabets and spaces.');
            allValid = false;
        } else {
            _showSuccess(namePick.el);
        }
    }

    // Mobile check
    if (mobilePick.el && (mobilePick.el.required || mobilePick.value)) {
        if (!_validateMobile(mobilePick.value)) {
            _showError(mobilePick.el, 'Mobile number must contain exactly 10 digits.');
            allValid = false;
        } else {
            _showSuccess(mobilePick.el);
        }
    }

    // Email check
    if (emailPick.el && (emailPick.el.required || emailPick.value)) {
        if (!_validateEmail(emailPick.value)) {
            _showError(emailPick.el, 'Please enter a valid email address.');
            allValid = false;
        } else {
            _showSuccess(emailPick.el);
        }
    }

    // Aadhaar check
    if (aadhaarEl && (aadhaarEl.required || aadhaarEl.value)) {
        if (!_validateAadhaar(aadhaarEl.value)) {
            _showError(aadhaarEl, 'Aadhaar number must contain exactly 12 digits.');
            allValid = false;
        } else {
            _showSuccess(aadhaarEl);
        }
    }

    // PAN check
    if (panEl && (panEl.required || panEl.value)) {
        if (!_validatePAN(panEl.value)) {
            _showError(panEl, 'PAN number must follow format like ABCDE1234F.');
            allValid = false;
        } else {
            _showSuccess(panEl);
        }
    }

    // IFSC check
    if (ifscEl && (ifscEl.required || ifscEl.value)) {
        if (!_validateIFSC(ifscEl.value)) {
            _showError(ifscEl, 'IFSC code must contain 11 characters.');
            allValid = false;
        } else {
            _showSuccess(ifscEl);
        }
    }

    // Account number check
    if (accountEl && (accountEl.required || accountEl.value)) {
        if (!_validateAccountNumber(accountEl.value)) {
            _showError(accountEl, 'Bank account number should contain only numeric values.');
            allValid = false;
        } else {
            _showSuccess(accountEl);
        }
    }

    // File uploads: ensure allowed types (PDF, JPG, JPEG, PNG)
    const allowedExt = ['pdf','jpg','jpeg','png'];
    const fileInputs = form.querySelectorAll('input[type="file"]');
    for (let fi of fileInputs) {
        if (!fi.files) continue;
        for (let i = 0; i < fi.files.length; i++) {
            const name = fi.files[i].name || '';
            const parts = name.split('.');
            if (parts.length < 2) {
                _showError(fi, 'Uploaded files must be PDF, JPG, JPEG or PNG.');
                allValid = false;
                continue;
            }
            const ext = parts.pop().toLowerCase();
            if (allowedExt.indexOf(ext) === -1) {
                _showError(fi, 'Uploaded files must be PDF, JPG, JPEG or PNG.');
                fi.focus();
                allValid = false;
            } else {
                _showSuccess(fi);
            }
        }
    }

    return allValid;
}

// Attach live validation to forms that use validateApplicationForm
document.addEventListener('DOMContentLoaded', function () {
    const forms = document.querySelectorAll('form[onsubmit]');
    forms.forEach(form => {
        if (form.getAttribute('onsubmit') && form.getAttribute('onsubmit').includes('validateApplicationForm')) {
            form.addEventListener('input', function (e) {
                // validate the form as user types to provide immediate feedback
                validateApplicationForm(form);
            });
            form.addEventListener('change', function (e) {
                validateApplicationForm(form);
            });
        }
    });
});