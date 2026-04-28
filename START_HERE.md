# ContractorHub Backend - Local Setup Guide

## ✅ What's Been Prepared

Your ContractorHub backend is **ready to run locally**! All files are in this folder.

### What you have:
- ✅ Virtual environment (venv/)
- ✅ All dependencies installed
- ✅ Django project structure
- ✅ Database migrations created (api/migrations/0001_initial.py)
- ✅ .env file with Railway credentials

## 🚀 To Run Locally on Your Mac

### Step 1: Activate Virtual Environment
```bash
cd ~/contractor_hub
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt.

### Step 2: Run Migrations
```bash
python manage.py migrate
```

This creates tables in your Railway PostgreSQL database.

### Step 3: Create Admin User
```bash
python manage.py createsuperuser
```

Follow the prompts to create your admin account.

### Step 4: Start the Server
```bash
python manage.py runserver
```

You should see:
```
Starting development server at http://localhost:8000/
```

### Step 5: Access Your Backend

- **API**: http://localhost:8000/api/
- **Admin Panel**: http://localhost:8000/admin/
- **Swagger Docs** (if enabled): http://localhost:8000/api/schema/

Log in with your superuser credentials.

## 📝 API Endpoints Available

All endpoints require authentication token. Get one by:
1. Go to http://localhost:8000/admin/
2. Log in with your superuser
3. Use the REST framework's Token Auth (if configured)

### Main Routes:
- `/api/company/` - Company management
- `/api/team-members/` - Team members
- `/api/projects/` - Projects (CRUD + custom actions)
- `/api/budgets/` - Budgets
- `/api/invoices/` - Invoices
- `/api/schedules/` - Project schedules

## 🔧 Database Notes

Your `.env` file has your **Railway PostgreSQL credentials**. When you run locally, Django will automatically connect to your Railway database.

Connection string: `postgresql://postgres:wwQlcfpXrYwmEnEoYBqMOPWbgEiMLMaU@postgres.railway.internal:5432/railway`

If you need to switch to local SQLite for testing (not recommended for production):
Update `DATABASES` in `contractor_hub/settings.py` to use SQLite.

## 🔌 QB Integration (Later)

QB integration is commented out for now. Once you get your QB Developer credentials:
1. Go to developer.intuit.com
2. Create an app
3. Get your Client ID and Client Secret
4. Add them to your .env file
5. Uncomment QB code in `api/views.py` and `api/urls.py`

## ❌ Troubleshooting

**Port 8000 already in use?**
```bash
python manage.py runserver 8001
```

**Database connection error?**
- Make sure .env file has correct Railway credentials
- Check that Railway PostgreSQL is online
- Try: `python manage.py dbshell` to test connection

**ModuleNotFoundError?**
```bash
pip install -r requirements.txt
```

## 📞 Next Steps

1. Run the server locally
2. Test the admin panel
3. Create sample projects/invoices via admin
4. Build your React frontend to consume these APIs
5. Connect QB integration when ready

---

**You're all set! Happy building! 🚀**
