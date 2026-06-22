from shiny import App, ui, render, reactive
import pandas as pd
import sqlite3
import ollama
import re


app_ui = ui.page_fluid(
    ui.h2("Ask Questions About CSV"),

    ui.input_file("file", "Upload CSV"),

    ui.navset_tab(
        ui.nav_panel(
            "Dataset Info",
            ui.h4("Basic Dataset Information"),
            ui.output_table("dataset_summary"),

            ui.h4("Column Names"),
            ui.output_table("column_names"),
        ),

        ui.nav_panel(
            "Ask Questions",
            ui.input_text("query", "Ask a question:"),

            ui.h4("Generated SQL"),
            ui.output_text_verbatim("sql_query"),

            ui.h4("Results"),
            ui.output_table("results"),
        ),
    )
)


def extract_select_sql(text):
    text = re.sub(r"```sql|```", "", text, flags=re.IGNORECASE).strip()

    match = re.search(r"(?is)\bselect\b.*?(?:;|$)", text)

    if not match:
        return None

    return match.group(0).strip().rstrip(";")


def server(input, output, session):

    @reactive.calc
    def dataframe():
        file = input.file()

        if not file:
            return None

        return pd.read_csv(file[0]["datapath"])

    @output
    @render.table
    def dataset_summary():
        df = dataframe()

        if df is None:
            return pd.DataFrame({
                "Information": ["Status"],
                "Value": ["No CSV uploaded yet"]
            })

        return pd.DataFrame({
            "Information": [
                "Number of rows",
                "Number of columns"
            ],
            "Value": [
                df.shape[0],
                df.shape[1]
            ]
        })

    @output
    @render.table
    def column_names():
        df = dataframe()

        if df is None:
            return pd.DataFrame()

        return pd.DataFrame({
            "Column Number": range(1, len(df.columns) + 1),
            "Column Name": df.columns.tolist()
        })

    @reactive.calc
    def generated_sql():
        df = dataframe()

        if not input.query() or df is None:
            return None

        columns = df.columns.tolist()

        prompt = f"""
Convert the user request into a SQLite SELECT query.

Table name: data
Columns: {columns}

Rules:
- Return exactly one SQL query
- The first word must be SELECT
- Use SELECT only
- Do not include markdown
- Do not include explanation
- Use double quotes around column names if they contain spaces

User request:
{input.query()}
"""

        response = ollama.chat(
            model="mistral",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        raw_sql = response["message"]["content"].strip()

        return extract_select_sql(raw_sql)

    @output
    @render.text
    def sql_query():
        sql = generated_sql()

        return sql if sql else "Upload a dataset and enter a query."

    @output
    @render.table
    def results():
        df = dataframe()
        sql = generated_sql()

        if df is None or sql is None:
            return pd.DataFrame()

        try:
            if not sql.lower().startswith("select"):
                return pd.DataFrame({
                    "Error": ["Only SELECT queries allowed"]
                })

            conn = sqlite3.connect(":memory:")

            df.to_sql(
                "data",
                conn,
                index=False,
                if_exists="replace"
            )

            result = pd.read_sql_query(sql, conn)

            conn.close()

            return result

        except Exception as e:
            return pd.DataFrame({
                "Error": [str(e)]
            })


app = App(app_ui, server)
