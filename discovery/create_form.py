"""
DealClaw -- Agent Discovery Interview
Builds a bilingual (English | Urdu) Google Form using the Forms API v1.

Every question title, section header, option label, and helper/description
text is written as "English | Urdu script".

Usage:
    python create_form.py

Requires credentials.json (OAuth Desktop client) in the same directory.
See the setup instructions provided alongside this script.
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
FORM_ID_FILE = "form_id.txt"


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
# Bilingual text helper
# ---------------------------------------------------------------------------

def bi(en, ur):
    return f"{en} | {ur}"


# ---------------------------------------------------------------------------
# Form-level text
# ---------------------------------------------------------------------------

FORM_TITLE = bi(
    "DealClaw — Agent Discovery Interview",
    "ڈیل کلا — ایجنٹ انٹرویو فارم",
)

FORM_DESCRIPTION = bi(
    "This form is part of DealClaw customer research. Your answers will help "
    "us build a better tool for real estate agents in Pakistan. All answers "
    "are confidential.",
    "یہ فارم ڈیل کلا کی کسٹمر ریسرچ کا "
    "حصہ ہے۔ آپ کے جوابات ہمیں پاکستان "
    "میں رئیل اسٹیٹ ایجنٹس کے لیے ایک بہتر "
    "ٹول بنانے میں مدد دیں گے۔ تمام جوابات "
    "خفیہ رکھے جائیں گے۔",
)

# The Forms REST API has no field for the post-submission confirmation
# message (that setting only exists in the Forms UI / Apps Script's
# FormApp.setConfirmationMessage). We still define it here and print it
# at the end so you can paste it in manually -- see the run instructions.
CONFIRMATION_MESSAGE = bi(
    "Thank you, your response has been recorded and the DealClaw team will "
    "contact you soon.",
    "شکریہ، آپ کا جواب محفوظ ہو گیا ہے اور "
    "ڈیل کلا ٹیم جلد آپ سے رابطہ کرے گی۔",
)


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def text_question(title_en, title_ur, required, paragraph=False,
                   helper_en=None, helper_ur=None):
    item = {
        "title": bi(title_en, title_ur),
        "questionItem": {
            "question": {
                "required": required,
                "textQuestion": {"paragraph": paragraph},
            }
        },
    }
    if helper_en is not None:
        item["description"] = bi(helper_en, helper_ur)
    return item


def choice_question(title_en, title_ur, required, options, choice_type="RADIO"):
    return {
        "title": bi(title_en, title_ur),
        "questionItem": {
            "question": {
                "required": required,
                "choiceQuestion": {
                    "type": choice_type,
                    "options": [{"value": bi(o_en, o_ur)} for o_en, o_ur in options],
                },
            }
        },
    }


def page_break(title_en, title_ur):
    return {
        "title": bi(title_en, title_ur),
        "pageBreakItem": {},
    }


# ---------------------------------------------------------------------------
# Items, in form order
# ---------------------------------------------------------------------------

ITEMS = [
    # --- Section 0: no header ---
    text_question(
        "What is your name?",
        "آپ کا نام کیا ہے؟",
        required=True,
    ),
    text_question(
        "Which city or area do you work in?",
        "آپ کس شہر یا علاقے میں کام کرتے ہیں؟",
        required=True,
        helper_en="e.g. DHA Karachi, Bahria Town, Gulshan",
        helper_ur="مثال کے طور پر ڈی ایچ ای کراچی، "
                  "بحریہ ٹاؤن، گلشن",
    ),
    text_question(
        "Agency name?",
        "ایجنسی کا نام؟",
        required=False,
        helper_en="Leave blank if working solo",
        helper_ur="اگر آپ اکیلے کام کرتے ہیں تو خالی چھوڑ دیں",
    ),

    # --- Section 1: Daily Reality ---
    page_break(
        "Daily Reality",
        "روزمرہ کی حقیقت",
    ),
    text_question(
        "How many leads come in on a typical day and from where?",
        "ایک عام دن میں کتنے لیڈز آتے ہیں اور "
        "کہاں سے آتے ہیں؟",
        required=True,
        paragraph=True,
    ),
    text_question(
        "What is the first thing you do in the morning?",
        "صبح سب سے پہلے آپ کیا کرتے ہیں؟",
        required=False,
        paragraph=True,
    ),
    choice_question(
        "How quickly do you reply when a lead comes in?",
        "جب کوئی لیڈ آتا ہے تو آپ کتنی جلدی "
        "جواب دیتے ہیں؟",
        required=True,
        options=[
            ("within 5 minutes", "5 منٹ کے اندر"),
            ("within 1 hour", "1 گھنٹے کے اندر"),
            ("a few hours", "چند گھنٹوں میں"),
            ("next day", "اگلے دن"),
            ("whenever free", "جب فرصت ملے"),
        ],
    ),
    choice_question(
        "Team size?",
        "ٹیم کا سائز؟",
        required=True,
        options=[
            ("solo", "اکیلا"),
            ("1 assistant", "1 اسسٹنٹ"),
            ("2 to 5 team", "2 سے 5 افراد کی ٹیم"),
            ("larger agency", "بڑی ایجنسی"),
        ],
    ),
    choice_question(
        "What property types do you deal in?",
        "آپ کن پراپرٹی اقسام میں کام کرتے ہیں؟",
        required=True,
        choice_type="CHECKBOX",
        options=[
            ("Residential plot", "رہائشی پلاٹ"),
            ("House or bungalow", "مکان یا بنگلہ"),
            ("Flat or apartment", "فلیٹ یا اپارٹمنٹ"),
            ("Commercial plot", "کمرشل پلاٹ"),
            ("Shop or office", "دکان یا دفتر"),
        ],
    ),
    choice_question(
        "Which area or scheme do you mostly work in?",
        "آپ زیادہ تر کس علاقے میں کام کرتے ہیں؟",
        required=True,
        options=[
            ("DHA", "ڈی ایچ اے"),
            ("Bahria Town", "بحریہ ٹاؤن"),
            ("Gulshan or Nazimabad", "گلشن یا ناظم آباد"),
            ("North Karachi or Surjani", "نارتھ کراچی یا سرجانی"),
            ("Other area", "دوسرا علاقہ"),
        ],
    ),

    # --- Section 2: Lead Management Pain ---
    page_break(
        "Lead Management Pain",
        "لیڈ مینیجمنٹ کے مسائل",
    ),
    choice_question(
        "How many leads slip through without a reply?",
        "کتنے لیڈز بغیر جواب کے رہ جاتے ہیں؟",
        required=True,
        options=[
            ("rarely", "شاذ و نادر"),
            ("a few per week", "ہفتے میں چند"),
            ("daily", "روزانہ"),
            ("constantly", "مسلسل"),
        ],
    ),
    text_question(
        "Leads per month?",
        "ماہانہ لیڈز کی تعداد؟",
        required=False,
        helper_en="e.g. 80",
        helper_ur="مثال کے طور پر 80",
    ),
    choice_question(
        "How long does it typically take from first contact to closing a deal?",
        "پہلے رابطے سے لے کر ڈیل مکمل ہونے تک عام "
        "طور پر کتنا وقت لگتا ہے؟",
        required=True,
        options=[
            ("Less than 1 week", "1 ہفتے سے کم"),
            ("1 to 4 weeks", "1 سے 4 ہفتے"),
            ("1 to 3 months", "1 سے 3 مہینے"),
            ("More than 3 months", "3 مہینے سے زیادہ"),
        ],
    ),
    text_question(
        "Deals closed per month?",
        "ماہانہ کتنے ڈیلز فائنل ہوتے ہیں؟",
        required=False,
        helper_en="e.g. 4",
        helper_ur="مثال کے طور پر 4",
    ),
    choice_question(
        "How do you currently track leads?",
        "آپ فی الحال لیڈز کو کیسے ٹریک کرتے ہیں؟",
        required=True,
        choice_type="CHECKBOX",
        options=[
            ("WhatsApp starred", "واٹس اےپ اسٹارڈ میسجز"),
            ("notebook diary", "نوٹ بک ڈائری"),
            ("Excel sheet", "ایکسل شیٹ"),
            ("CRM software", "سی آر ایم سافٹ ویئر"),
            ("memory only", "صرف یادداشت سے"),
            ("nothing", "کچھ بھی نہیں"),
        ],
    ),
    text_question(
        "Has a hot lead ever slipped away because you were busy? Tell the story.",
        "کیا کبھی کوئی اہم لیڈ آپ کے مصروف ہونے کی "
        "وجہ سے ہاتھ سے نکل گیا؟ واقعہ بتائیں۔",
        required=False,
        paragraph=True,
    ),

    # --- Section 3: Qualifying and Filtering ---
    page_break(
        "Qualifying and Filtering",
        "جانچ اور فلٹرنگ",
    ),
    text_question(
        "How do you decide if an inquiry is serious or a time-waster?",
        "آپ کیسے فیصلہ کرتے ہیں کہ کوئی انکوائری "
        "سنجیدہ ہے یا وقت ضائع کرنے "
        "والی؟",
        required=True,
        paragraph=True,
    ),
    choice_question(
        "What percent of inquiries are time-wasters?",
        "کتنے فیصد انکوائریز وقت ضائع کرنے "
        "والی ہوتی ہیں؟",
        required=True,
        options=[
            ("less than 20 percent", "20 فیصد سے کم"),
            ("20 to 40 percent", "20 سے 40 فیصد"),
            ("40 to 60 percent", "40 سے 60 فیصد"),
            ("more than 60 percent", "60 فیصد سے زیادہ"),
        ],
    ),
    choice_question(
        "Do you ask about budget first or show property first?",
        "کیا آپ پہلے بجٹ پوچھتے ہیں یا پہلے "
        "پراپرٹی دکھاتے ہیں؟",
        required=True,
        options=[
            ("budget first", "پہلے بجٹ"),
            ("property first", "پہلے پراپرٹی"),
            ("depends on client", "کلائنٹ پر منحصر ہے"),
        ],
    ),
    choice_question(
        "Who usually makes the final decision to buy?",
        "عام طور پر خریداری کا حتمی فیصلہ کون کرتا ہے؟",
        required=True,
        options=[
            ("The buyer themselves", "خود خریدار"),
            ("Husband and wife together", "میاں بیوی مل کر"),
            ("Whole family decides", "پورا گھر مل کر"),
            ("Investor decides alone", "سرمایہ کار اکیلا فیصلہ کرتا ہے"),
        ],
    ),

    # --- Section 4: Channels and Platforms ---
    page_break(
        "Channels and Platforms",
        "چینلز اور پلیٹ فارمز",
    ),
    choice_question(
        "Which platforms do you use?",
        "آپ کون سے پلیٹ فارمز استعمال کرتے ہیں؟",
        required=True,
        choice_type="CHECKBOX",
        options=[
            ("Zameen.com", "Zameen.com"),
            ("OLX", "OLX"),
            ("Facebook Groups", "فیس بک گروپس"),
            ("Facebook Marketplace", "فیس بک مارکیٹ پلیس"),
            ("WhatsApp Broadcast", "واٹس اےپ براڈ کاسٹ"),
            ("Instagram", "انسٹاگرام"),
            ("Propforce", "Propforce"),
            ("Walk-ins and referrals", "واک انز اور ریفرلز"),
        ],
    ),
    choice_question(
        "Do you use WhatsApp Business auto-reply?",
        "کیا آپ واٹس ایپ بزنس آٹو ری پلائی "
        "استعمال کرتے ہیں؟",
        required=True,
        options=[
            ("Yes with auto-reply set", "جی ہاں، آٹو ری پلائی سیٹ ہے"),
            ("Yes but no auto-reply", "جی ہاں لیکن آٹو ری پلائی نہیں"),
            ("No just regular WhatsApp", "نہیں، صرف عام واٹس ایپ"),
            ("No WhatsApp at all", "نہیں، واٹس ایپ استعمال نہیں کرتا"),
        ],
    ),
    choice_question(
        "Which platform gives the best quality leads?",
        "کون سا پلیٹ فارم بہترین کوالٹی کے "
        "لیڈز دیتا ہے؟",
        required=True,
        options=[
            ("Zameen.com", "Zameen.com"),
            ("OLX", "OLX"),
            ("Facebook", "فیس بک"),
            ("WhatsApp", "واٹس اےپ"),
            ("Referrals", "ریفرلز"),
        ],
    ),
    choice_question(
        "Have you used any CRM or property software before?",
        "کیا آپ نے پہلے کوئی سی آر ایم یا پراپرٹی "
        "سافٹ ویئر استعمال کیا ہے؟",
        required=True,
        options=[
            ("never", "کبھی نہیں"),
            ("tried but stopped", "آزمایا لیکن چھوڑ دیا"),
            ("currently using", "فی الحال استعمال کر رہے ہیں"),
        ],
    ),
    text_question(
        "If yes which one and why did you stop?",
        "اگر ہاں، تو کون سا اور آپ نے کیوں چھوڑا؟",
        required=False,
        paragraph=True,
    ),

    # --- Section 5: Revenue and Willingness to Pay ---
    page_break(
        "Revenue and Willingness to Pay",
        "آمدنی اور ادائیگی کی رضامندی",
    ),
    text_question(
        "If one deal slips how much commission is lost in Rupees?",
        "اگر ایک ڈیل ہاتھ سے نکل جائے تو کتنے "
        "روپے کمیشن کا نقصان ہوتا ہے؟",
        required=True,
        helper_en="e.g. 50000",
        helper_ur="مثال کے طور پر 50000",
    ),
    choice_question(
        "If a tool automatically scored leads as serious or not would you use it?",
        "اگر کوئی ٹول خودکار طریقے سے لیڈز کو "
        "سنجیدہ یا غیر سنجیدہ کے طور پر اسکور "
        "کرے تو کیا آپ اسے استعمال کریں گے؟",
        required=True,
        options=[
            ("yes definitely", "جی ہاں بالکل"),
            ("maybe", "شاید"),
            ("need to see it first", "پہلے دیکھنا چاہوں گا"),
            ("no", "نہیں"),
        ],
    ),
    choice_question(
        "What would you pay monthly for such a tool?",
        "اس طرح کے ٹول کے لیے آپ ماہانہ کتنی "
        "ادائیگی کریں گے؟",
        required=True,
        options=[
            ("Rs 1000 to 2000", "1000 سے 2000 روپے"),
            ("Rs 3000 to 5000", "3000 سے 5000 روپے"),
            ("Rs 6000 to 10000", "6000 سے 10000 روپے"),
            ("Rs 10000 or more", "10000 روپے یا زیادہ"),
            ("nothing free only", "کچھ نہیں، صرف مفت"),
        ],
    ),
    text_question(
        "Any other frustrations not covered above?",
        "کوئی اور مسئلہ جو اوپر بیان نہیں ہوا؟",
        required=False,
        paragraph=True,
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
                "documentTitle": "DealClaw Agent Discovery Interview",
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
