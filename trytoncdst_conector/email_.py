import mimetypes
from email.encoders import encode_base64
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses

from trytond.config import config
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.sendmail import SMTPDataManager, sendmail_transactional
from trytond.transaction import Transaction

try:
    import html2text
except ImportError:
    html2text = None

HTML_EMAIL = """<!DOCTYPE html>
<html>
<head><title>%(subject)s</title></head>
<body>%(body)s<br/>
<hr style="width: 2em; text-align: start; display: inline-block"/><br/>
%(signature)s</body>
</html>"""


def _get_emails(value):
    "Return list of email from the comma separated list"
    return [e for n, e in getaddresses([value]) if e]


class Email(metaclass=PoolMeta):
    "Email"
    __name__ = 'ir.email'

    @classmethod
    def send(cls,
             to='',
             cc='',
             bcc='',
             subject='',
             body='',
             files=None,
             record=None,
             reports=None,
             attachments=None):
        pool = Pool()
        User = pool.get('res.user')
        ActionReport = pool.get('ir.action.report')
        Attachment = pool.get('ir.attachment')
        ConfigEmail = pool.get('conector.email')
        emails = ConfigEmail.search([])

        if not emails:
            raise UserError('Error email: ',
                            'No se encontro informacion para envio de emails')
        transaction = Transaction()
        user = User(transaction.user)
        email = emails[0]
        Model = pool.get(record[0])
        record = Model(record[1])

        body_html = HTML_EMAIL % {
            'subject': subject,
            'body': body,
            'signature': user.signature or '',
        }
        content = MIMEMultipart('alternative')
        if html2text:
            body_text = HTML_EMAIL % {
                'subject': subject,
                'body': body,
                'signature': '',
            }
            converter = html2text.HTML2Text()
            body_text = converter.handle(body_text)
            if user.signature:
                body_text += '\n-- \n' + converter.handle(user.signature)
            part = MIMEText(body_text, 'plain', _charset='utf-8')
            content.attach(part)
        part = MIMEText(body_html, 'html', _charset='utf-8')
        content.attach(part)
        if files or reports or attachments:
            msg = MIMEMultipart('mixed')
            msg.attach(content)
            if files is None:
                files = []
            else:
                files = list(files)

            for report_id in (reports or []):
                report = ActionReport(report_id)
                Report = pool.get(report.report_name, type='report')
                ext, content, _, title = Report.execute([record.id], {
                    'action_id': report.id,
                })
                name = '%s.%s' % (title, ext)
                if isinstance(content, str):
                    content = content.encode('utf-8')
                files.append((name, content))
            if attachments:
                files += [(a.name, a.data)
                          for a in Attachment.browse(attachments)]
            for name, data in files:
                mimetype, _ = mimetypes.guess_type(name)
                if mimetype:
                    attachment = MIMENonMultipart(*mimetype.split('/'))
                    attachment.set_payload(data)
                    encode_base64(attachment)
                else:
                    attachment = MIMEApplication(data)
                attachment.add_header('Content-Disposition',
                                      'attachment',
                                      filename=('utf-8', '', name))
                msg.attach(attachment)
        else:
            msg = content
        msg['From'] = from_ = email.from_to
        if user.email:
            if user.name:
                user_email = formataddr((user.name, user.email))
            else:
                user_email = user.email
            msg['Behalf-Of'] = user_email
            msg['Reply-To'] = user_email
        msg['To'] = ', '.join(formataddr(a) for a in getaddresses([to]))
        msg['Cc'] = ', '.join(formataddr(a) for a in getaddresses([cc]))
        msg['Subject'] = Header(subject, 'utf-8')

        to_addrs = list(
            filter(
                None,
                map(str.strip,
                    _get_emails(to) + _get_emails(cc) + _get_emails(bcc))))
        sendmail_transactional(from_,
                               to_addrs,
                               msg,
                               datamanager=SMTPDataManager(strict=True))

        email = cls(recipients=to,
                    recipients_secondary=cc,
                    recipients_hidden=bcc,
                    addresses=[{
                        'address': a
                    } for a in to_addrs],
                    subject=subject,
                    body=body,
                    resource=record)
        email.save()
        if files:
            with Transaction().set_context(_check_access=False):
                attachments_ = []
                for name, data in files:
                    attachments_.append(
                        Attachment(resource=email, name=name, data=data))
                Attachment.save(attachments_)
        return email
