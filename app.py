import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import datetime
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---- Configurazione Google API (inserisci il tuo file JSON di servizio o OAuth) ----
# Esempio con Service Account (meglio OAuth per uso personale, questa è demo semplificata)
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/tasks.readonly']
SERVICE_ACCOUNT_FILE = 'google-credentials.json'   # <-- Inserisci qui il tuo file credenziali

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

calendar_service = build('calendar', 'v3', credentials=credentials)
tasks_service = build('tasks', 'v1', credentials=credentials)

# ---- Funzioni per recuperare dati ----
def get_todays_events(service):
    now = datetime.datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    end_of_day = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary', timeMin=start_of_day, timeMax=end_of_day,
        singleEvents=True, orderBy='startTime').execute()
    events = events_result.get('items', [])
    return events

def get_todays_tasks(service):
    tasks_list = service.tasks().list(tasklist='@default').execute()
    today = datetime.datetime.utcnow().date()
    tasks = []
    for task in tasks_list.get('items', []):
        due = task.get('due')
        if due:
            due_date = datetime.datetime.fromisoformat(due[:-1]).date()
            if due_date == today:
                tasks.append(task)
    return tasks

# ---- Layout Dash + Bootstrap ----
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

def render_events(events):
    if not events:
        return html.P("Nessun appuntamento oggi.")
    return dbc.ListGroup([
        dbc.ListGroupItem([
            html.B(event['summary']),
            html.Br(),
            f"{event['start'].get('dateTime', event['start'].get('date'))} - "
            f"{event['end'].get('dateTime', event['end'].get('date'))}"
        ]) for event in events
    ])

def render_tasks(tasks):
    if not tasks:
        return html.P("Nessun task per oggi.")
    return dbc.ListGroup([
        dbc.ListGroupItem(task['title']) for task in tasks
    ])

app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H2("Dashboard Giornaliera"), width=12)
    ], className="my-3"),
    dbc.Row([
        dbc.Col([
            html.H4("Appuntamenti di oggi"),
            html.Div(id='events-list')
        ], xs=12, md=6),
        dbc.Col([
            html.H4("Task di oggi"),
            html.Div(id='tasks-list')
        ], xs=12, md=6)
    ]),
    dcc.Interval(id='interval', interval=5*60*1000, n_intervals=0) # refresh ogni 5 min
], fluid=True)

@app.callback(
    dash.dependencies.Output('events-list', 'children'),
    dash.dependencies.Output('tasks-list', 'children'),
    dash.dependencies.Input('interval', 'n_intervals')
)
def update_dashboard(n):
    events = get_todays_events(calendar_service)
    tasks = get_todays_tasks(tasks_service)
    return render_events(events), render_tasks(tasks)

if __name__ == '__main__':
    app.run_server(debug=True)
