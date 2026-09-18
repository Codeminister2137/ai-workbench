import os
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
import yagmail

SENT_FILE = 'sent_emails.txt'
if os.path.exists(SENT_FILE):
    with open(SENT_FILE, 'r') as f:
        sent_emails = set(line.strip() for line in f.readlines())
else:
    sent_emails = set()

class Config(BaseSettings):
    GMAIL_PASSWORD: str
    GMAIL_EMAIL: str
    model_config = SettingsConfigDict(env_file='.env')

config = Config()

yag = yagmail.SMTP(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
emails = sys.argv[1:]
print(emails)
for email in emails:
    if email in sent_emails:
        print(f'Skipped {email}')
        continue
    yag.send(to=email,
    subject = 'Python Developer - Application',
    contents= "Hi,\n\n"
              "I came across your company while looking for teams working with modern backend technologies, and I wanted to reach out. "
              "I am a Python developer with experience in Django, FastAPI and other frameworks. I also expanded my knowledge in Data and AI fields.\n"
              "I wanted to ask if you are currently looking to expand your team or might have openings for a remote developer based in Poland. "
              "I would be very excited to contribute to your projects and help your team grow. "
              "I have attached my CV for your review, and here is a link to my portfolio: https://github.com/Codeminister2137\n"
              "Thank you for your time, and I look forward to hearing from you.\n\n"
              "Best regards,\n"
              "Jakub Jaworski\n"
              "+48 572 691 947\n"
              "LinkedIn: https://www.linkedin.com/in/jakub-jaworski-512966270/",
    attachments = 'Jakub_Jaworski_Backend_Developer_CV_ENG.pdf')
    with open(SENT_FILE, 'a') as f:
        f.write(email + '\n')
    #  Add domain names to exclusion list "@zf.com"
    sent_emails.add(email)