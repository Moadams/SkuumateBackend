# SkuuMate Backend

A comprehensive Django REST API for managing educational institutions, including academics, attendance, exams, finance, and subscriptions management.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Configuration](#environment-configuration)
- [Database Migrations](#database-migrations)
- [Database Seeds](#database-seeds)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)

## Prerequisites

### For Docker Setup (Recommended)
- Docker Engine 20.10+
- Docker Compose 1.29+

### For Local Development
- Python 3.12+
- pip (Python package manager)
- MySQL Server 8.0+ or PostgreSQL 12+
- Redis 7.0+
- virtualenv or venv

## Installation

### Option 1: Docker Setup (Recommended)

This is the easiest way to get started as all services are containerized.

1. **Clone the repository** (if not already done):
```bash
git clone <repository-url>
cd skuumate/backend
```

2. **Create environment file**:
Copy the `.env.example` to `.env` and update the values:
```bash
cp .env.example .env
```

3. **Build and start containers**:
```bash
docker-compose up --build
```

The application will automatically:
- Wait for the database to be ready
- Run migrations
- Collect static files
- Seed the database with initial data
- Start the API server

**Services will be available at:**
- API: `http://localhost:8000`
- Adminer (Database GUI): `http://localhost:8080`
- Redis: `localhost:6379`

### Option 2: Local Development Setup

1. **Clone the repository**:
```bash
git clone <repository-url>
cd skuumate/backend
```

2. **Create virtual environment**:
```bash
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Create environment file**:
```bash
# Create .env file with required variables (see Environment Configuration section)
touch .env
```

5. **Configure database** (update in `.env`):
```
DB_ENGINE=django.db.backends.postgresql  # or django.db.backends.mysql
DB_HOST=localhost
DB_PORT=5432  # 3306 for MySQL
DB_NAME=skuumate_db
DB_USER=postgres
DB_PASSWORD=your_password
```

6. **Apply migrations**:
```bash
python manage.py migrate
```

7. **Run seeds** (optional - see Database Seeds section):
```bash
python manage.py seed
```

8. **Start development server**:
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000`

## Environment Configuration

Create a `.env` file in the backend root directory with the following variables:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=skuumate_db
DB_USER=postgres
DB_PASSWORD=postgres

# Redis Configuration
REDIS_URL=redis://localhost:6379/1

# CORS Settings
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Email Configuration (if using email features)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### Docker Database Configuration

The `docker-compose.yml` uses PostgreSQL by default with these credentials:
```
Database: skuumate_db
User: postgres
Password: postgres
Host: db (in Docker network)
```

## Database Migrations

Migrations are automatically applied when running with Docker, but you can also run them manually:

### Run all pending migrations:
```bash
python manage.py migrate
```

### Run migrations for a specific app:
```bash
python manage.py migrate academics
python manage.py migrate accounts
python manage.py migrate schools
# etc...
```

### Create new migrations after model changes:
```bash
python manage.py makemigrations
```

### Rollback to a specific migration:
```bash
python manage.py migrate <app_name> <migration_number>
# Example: python manage.py migrate academics 0005
```

## Database Seeds

The application includes seed data to initialize the database with necessary information.

### Available Seed Commands

#### 1. **Full Seed** (Recommended for initial setup)
Runs all seeders in the correct order:
```bash
python manage.py seed
```

**This will seed:**
- Subscription Plans
- Superadmin User (with custom credentials)
- System Staff Positions

**Optional parameters:**
```bash
python manage.py seed \
  --email superadmin@skuumate.com \
  --password Admin@1234 \
  --first-name Super \
  --last-name Admin
```

#### 2. **Seed Superadmin User (Individual)**
Create or update the superadmin user:
```bash
python manage.py seed_superadmin \
  --email admin@skuumate.com \
  --password SecurePassword@123 \
  --first-name Admin \
  --last-name User
```

**Default values:**
- Email: `superadmin@skuumate.com`
- Password: `Admin@1234`
- First Name: `Super`
- Last Name: `Admin`

### Seed Execution Flow

When running `python manage.py seed`, the following happens in order:

1. **Subscription Plans** - Creates default subscription tiers
2. **Superadmin User** - Creates the superadmin account
3. **Staff Positions** - Creates system staff positions

**Note:** Seeds are idempotent - running them multiple times won't create duplicates.

### Docker Automatic Seeding

When using Docker, seeds are automatically run on first startup via the `entrypoint.sh` script. You can see the seeding process in the logs:

```bash
docker-compose logs backend
```

## Running the Application

### Using Docker (Recommended)

**Start all services:**
```bash
docker-compose up
```

**Start in background:**
```bash
docker-compose up -d
```

**View logs:**
```bash
docker-compose logs -f backend
```

**Stop services:**
```bash
docker-compose down
```

**Full restart:**
```bash
docker-compose down && docker-compose up --build
```

### Local Development

**Start development server:**
```bash
python manage.py runserver
```

**With custom port:**
```bash
python manage.py runserver 0.0.0.0:8080
```

**Clear cache:**
```bash
python manage.py clearcache
```

## API Documentation

### Base URL
- Local: `http://localhost:8000/api/v1/`
- Docker: `http://localhost:8000/api/v1/`

### Admin Panel
- URL: `http://localhost:8000/admin/`
- Credentials: Use the superadmin account created during setup

### Authentication

The API uses JWT (JSON Web Tokens) for authentication.

**Login endpoint:**
```
POST /api/v1/auth/login/
```

**Request body:**
```json
{
  "email": "superadmin@skuumate.com",
  "password": "Admin@1234"
}
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Include token in requests:**
```
Authorization: Bearer <access_token>
```

### Main API Endpoints

| Module | Endpoints |
|--------|-----------|
| **Accounts** | `/accounts/` |
| **Schools** | `/schools/` |
| **Academics** | `/academics/`, `/subjects/`, `/classes/` |
| **Students** | `/students/` |
| **Attendance** | `/attendance/` |
| **Exams** | `/exams/`, `/grades/` |
| **Staff** | `/staff/` |
| **Subscriptions** | `/subscriptions/`, `/plans/` |

## Project Structure

```
backend/
├── academics/           # Academic module (subjects, classes, grading)
├── accounts/           # User authentication and management
├── attendance/         # Attendance tracking
├── core/              # Core utilities, pagination, permissions
├── exams/             # Examinations management
├── finance/           # Financial management
├── media/             # User uploads (profile pictures, documents)
├── schools/           # School management
├── staff/             # Staff management
├── students/          # Student management
├── subscriptions/     # Subscription and payment plans
├── skuumate/          # Django project settings
├── Dockerfile         # Docker image definition
├── docker-compose.yml # Docker compose configuration
├── entrypoint.sh      # Startup script for Docker
├── manage.py          # Django management script
├── requirements.txt   # Python dependencies
└── db.sqlite3         # SQLite database (local development)
```

### Key Files

- `skuumate/settings.py` - Django settings and configuration
- `skuumate/urls.py` - Main URL routing
- `requirements.txt` - Python package dependencies
- `docker-compose.yml` - Services configuration (PostgreSQL, Redis, Backend)
- `Dockerfile` - Backend container definition

## Troubleshooting

### Database Connection Issues

**Docker:**
```bash
# Check if database is running
docker-compose ps

# View database logs
docker-compose logs db

# Restart services
docker-compose restart db
```

**Local:**
- Ensure MySQL/PostgreSQL service is running
- Check `.env` database credentials
- Verify database exists: `CREATE DATABASE skuumate_db;`

### Migration Errors

```bash
# Show migration status
python manage.py showmigrations

# Fake initial migration if needed
python manage.py migrate --fake-initial
```

### Redis Connection Issues

**Docker:**
```bash
# Check Redis status
docker-compose logs redis

# Test Redis connection
docker-compose exec redis redis-cli ping
```

### Permission Errors

Ensure proper permissions in media and staticfiles directories:
```bash
chmod -R 755 media/
chmod -R 755 staticfiles/
```

## Development Tips

- Use `python manage.py shell` to interact with the database interactively
- Install `django-extensions` for additional management commands
- Use Adminer (`http://localhost:8080`) to browse the database visually
- Check the admin panel at `/admin/` for data management

## Contributing

When adding new features:
1. Create migrations for model changes: `python manage.py makemigrations`
2. Write tests in the respective app's `tests.py`
3. Follow Django best practices and project conventions
4. Update this README if adding new seeds or configuration options

## Support

For issues or questions:
- Check existing documentation in the codebase
- Review Django REST Framework [documentation](https://www.django-rest-framework.org/)
- Check Django [documentation](https://docs.djangoproject.com/)
