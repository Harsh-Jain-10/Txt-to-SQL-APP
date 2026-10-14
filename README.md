# Text-to-SQL App

A lightweight Python application that translates natural language questions into PostgreSQL queries using the Groq API and executes them against a sales database.

## Features
- **Natural Language to SQL**: Converts plain English prompts into valid PostgreSQL queries.
- **Groq API Integration**: Fast query generation powered by Groq LLM inference.
- **PostgreSQL Execution**: Connects via `psycopg2` to run generated queries against `digital_store_sales` and return tabular results.

## Project Structure
```text
├── generate_sql.py     # Main application script
├── test_connection.py  # Quick script to verify PostgreSQL connectivity
├── .env.example        # Environment variable template
├── requirements.txt    # Project dependencies
└── README.md           # Documentation
```

## Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Harsh-Jain-10/Txt-to-SQL-APP.git
cd Txt-to-SQL-APP
```

### 2. Set Up Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your database credentials and Groq API key:
```env
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=digital_store
LLM_API_KEY=your_groq_api_key
```

## Usage

Test database connectivity:
```bash
python test_connection.py
```

Run natural language queries:
```bash
python generate_sql.py
```
