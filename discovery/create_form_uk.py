"""
DealClaw -- UK Agent Discovery Interview
Builds an English-only Google Form using the Forms API v1.

Usage:
    python create_form_uk.py

Requires credentials.json (OAuth Desktop client) in the same directory.
Reuses token.json if present so it does not ask you to log in again.
"""

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/forms.body"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
FORM_ID_FILE = "form_id_uk.txt"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


# ---------------------------------------------------------------------------
# Form-level text
# ---------------------------------------------------------------------------

FORM_TITLE = "DealClaw — UK Agent Discovery Interview"

FORM_DESCRIPTION = (
    "This form is part of DealClaw customer research for the UK market. "
    "Your answers will help us build a better lead management tool for "
    "estate agents. All answers are confidential and will only be used "
    "for product development."
)

# The Forms REST API has no field for the post-submission confirmation
# message (that setting only exists in the Forms UI / Apps Script's
# FormApp.setConfirmationMessage). We still define it here and print it
# at the end so you can paste it in manually -- see the run instructions.
CONFIRMATION_MESSAGE = (
    "Thank you for your time. Your response has been recorded. The "
    "DealClaw team will be in touch soon."
)


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def text_question(title, required, paragraph=False, helper=None):
    item = {
        "title": title,
        "questionItem": {
            "question": {
                "required": required,
                "textQuestion": {"paragraph": paragraph},
            }
        },
    }
    if helper is not None:
        item["description"] = helper
    return item


def choice_question(title, required, options, choice_type="RADIO"):
    return {
        "title": title,
        "questionItem": {
            "question": {
                "required": required,
                "choiceQuestion": {
                    "type": choice_type,
                    "options": [{"value": o} for o in options],
                },
            }
        },
    }


def page_break(title):
    return {
        "title": title,
        "pageBreakItem": {},
    }


# ---------------------------------------------------------------------------
# Items, in form order
# ---------------------------------------------------------------------------

ITEMS = [
    # --- Section 0: no header ---
    text_question(
        "What is your name?",
        required=True,
    ),
    text_question(
        "Which city or area do you work in?",
        required=True,
        helper="e.g. London, Manchester, Birmingham, Leeds",
    ),
    text_question(
        "Agency name?",
        required=False,
        helper="Leave blank if independent",
    ),
    choice_question(
        "What is your role?",
        required=True,
        options=[
            "Independent estate agent",
            "Branch manager",
            "Senior negotiator",
            "Junior negotiator",
            "Other",
        ],
    ),
    choice_question(
        "What property types do you specialise in?",
        required=True,
        choice_type="CHECKBOX",
        options=[
            "Residential sales",
            "Residential lettings",
            "Commercial sales",
            "Commercial lettings",
            "New developments",
            "Land and investments",
        ],
    ),

    # --- Section 1: Daily Reality ---
    page_break("Daily Reality"),
    text_question(
        "How many leads or enquiries come in on a typical day and from where?",
        required=True,
        paragraph=True,
    ),
    text_question(
        "Walk me through your morning routine — what do you check first?",
        required=False,
        paragraph=True,
    ),
    choice_question(
        "How quickly do you typically respond to a new enquiry?",
        required=True,
        options=[
            "Within 5 minutes",
            "Within 1 hour",
            "Within a few hours",
            "Same day",
            "Next day or later",
        ],
    ),
    choice_question(
        "Team size at your branch?",
        required=True,
        options=[
            "Just me",
            "2 to 5 people",
            "6 to 10 people",
            "More than 10 people",
        ],
    ),

    # --- Section 2: Lead Management Pain ---
    page_break("Lead Management Pain"),
    choice_question(
        "How often do leads slip through without a response?",
        required=True,
        options=[
            "Rarely",
            "A few per week",
            "Daily",
            "Constantly — it is a real problem",
        ],
    ),
    text_question(
        "Roughly how many enquiries do you receive per month?",
        required=False,
        helper="e.g. 120",
    ),
    text_question(
        "How many convert to viewings or instructions per month?",
        required=False,
        helper="e.g. 15",
    ),
    text_question(
        "What is the average days on market for properties in your area currently?",
        required=False,
        helper="e.g. 45 days",
    ),
    choice_question(
        "How do you currently track leads and enquiries?",
        required=True,
        choice_type="CHECKBOX",
        options=[
            "Spreadsheet",
            "CRM system",
            "Email inbox",
            "Paper notes",
            "Nothing formal",
            "Other",
        ],
    ),
    choice_question(
        "If you use a CRM which one?",
        required=True,
        options=[
            "Reapit",
            "Jupix",
            "AgentPro",
            "Alto",
            "Dezrez",
            "Salesforce",
            "HubSpot",
            "No CRM",
            "Other",
        ],
    ),
    choice_question(
        "Beyond your CRM what tools does your team use day to day?",
        required=True,
        choice_type="CHECKBOX",
        options=[
            "WhatsApp",
            "Slack",
            "Microsoft Teams",
            "Email only",
            "Phone calls only",
            "Shared spreadsheet",
            "Nothing formal",
        ],
    ),
    text_question(
        "Has a valuable lead ever been lost simply because no one followed up "
        "in time? Tell us what happened.",
        required=False,
        paragraph=True,
    ),

    # --- Section 3: Qualifying and Filtering ---
    page_break("Qualifying and Filtering"),
    text_question(
        "How do you currently decide whether an enquiry is worth pursuing or "
        "is a time-waster?",
        required=True,
        paragraph=True,
    ),
    choice_question(
        "What percentage of your enquiries would you say are low quality or "
        "time-wasters?",
        required=True,
        options=[
            "Less than 20%",
            "20 to 40%",
            "40 to 60%",
            "More than 60%",
        ],
    ),
    choice_question(
        "What is your biggest frustration with incoming enquiries?",
        required=True,
        options=[
            "Too many low quality leads",
            "Slow response time from my team",
            "No central place to track them",
            "Duplicate enquiries from multiple portals",
            "Hard to tell serious buyers from browsers",
        ],
    ),

    # --- Section 4: Channels and Portals ---
    page_break("Channels and Portals"),
    choice_question(
        "Which portals or channels do you use to generate leads?",
        required=True,
        choice_type="CHECKBOX",
        options=[
            "Rightmove",
            "Zoopla",
            "OnTheMarket",
            "PrimeLocation",
            "Facebook",
            "Instagram",
            "Google Ads",
            "Referrals and word of mouth",
            "Walk-ins",
            "Other",
        ],
    ),
    choice_question(
        "Which portal gives you the best quality leads?",
        required=True,
        options=[
            "Rightmove",
            "Zoopla",
            "OnTheMarket",
            "Referrals",
            "Social media",
            "Other",
        ],
    ),
    choice_question(
        "How satisfied are you with the lead quality from portals overall?",
        required=True,
        options=[
            "Very satisfied",
            "Somewhat satisfied",
            "Neutral",
            "Somewhat dissatisfied",
            "Very dissatisfied",
        ],
    ),
    choice_question(
        "How confident are you that your current lead handling process is "
        "fully GDPR compliant?",
        required=True,
        options=[
            "Very confident — we have a clear process",
            "Somewhat confident",
            "Not sure — we have not reviewed it recently",
            "Concerned — we know there are gaps",
        ],
    ),
    text_question(
        "What do you wish the portals did better when it comes to lead "
        "quality or information?",
        required=False,
        paragraph=True,
    ),

    # --- Section 5: Revenue and Willingness to Pay ---
    page_break("Revenue and Willingness to Pay"),
    choice_question(
        "What is your average commission on a completed sale?",
        required=True,
        options=[
            "Under 1%",
            "1 to 1.5%",
            "1.5 to 2%",
            "Over 2%",
            "Fixed fee",
        ],
    ),
    choice_question(
        "If a tool automatically qualified and scored every inbound lead so "
        "your team only spent time on serious buyers — would you use it?",
        required=True,
        options=[
            "Yes definitely",
            "Probably yes",
            "Maybe — depends on the price",
            "Unlikely",
            "No",
        ],
    ),
    choice_question(
        "What would you be willing to pay per month for such a tool?",
        required=True,
        options=[
            "Under 50 GBP",
            "50 to 100 GBP",
            "100 to 200 GBP",
            "200 to 500 GBP",
            "Over 500 GBP",
            "Nothing — it would need to be free",
        ],
    ),
    choice_question(
        "How would you prefer to pay?",
        required=True,
        options=[
            "Monthly subscription",
            "Annual subscription with discount",
            "Per lead processed",
            "One-time setup fee",
        ],
    ),
    text_question(
        "Any other pain points or frustrations with your current lead "
        "management process that we have not covered?",
        required=False,
        paragraph=True,
    ),
    text_question(
        "If you would be open to a short follow-up call please leave your "
        "email or phone number.",
        required=False,
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    creds = get_credentials()
    service = build("forms", "v1", credentials=creds)

    # forms.create only accepts info.title/documentTitle -- documentTitle is
    # read-only after creation, so it must be set here, not via batchUpdate.
    form = service.forms().create(
        body={
            "info": {
                "title": FORM_TITLE,
                "documentTitle": "DealClaw UK Agent Discovery Interview",
            }
        }
    ).execute()
    form_id = form["formId"]

    requests_body = [
        {
            "updateFormInfo": {
                "info": {
                    "description": FORM_DESCRIPTION,
                },
                "updateMask": "description",
            }
        }
    ]

    for index, item in enumerate(ITEMS):
        requests_body.append(
            {
                "createItem": {
                    "item": item,
                    "location": {"index": index},
                }
            }
        )

    service.forms().batchUpdate(
        formId=form_id, body={"requests": requests_body}
    ).execute()

    result = service.forms().get(formId=form_id).execute()
    edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    responder_url = result.get(
        "responderUri", f"https://docs.google.com/forms/d/{form_id}/viewform"
    )

    with open(FORM_ID_FILE, "w", encoding="utf-8") as f:
        f.write(form_id)

    print("Form created successfully.")
    print(f"Form ID:   {form_id}")
    print(f"Edit URL:  {edit_url}")
    print(f"Share URL: {responder_url}")
    print()
    print("NOTE: The Forms REST API has no field for the post-submission")
    print("confirmation message -- it can only be set from the Forms UI or")
    print("Apps Script. Set it manually:")
    print("  Edit form -> Settings (gear icon) -> Presentation -> Confirmation message")
    print("Paste this text:")
    print(CONFIRMATION_MESSAGE)
    print()
    print("Newly created forms accept responses by default, so no separate")
    print("'publish' step is required.")


if __name__ == "__main__":
    main()
