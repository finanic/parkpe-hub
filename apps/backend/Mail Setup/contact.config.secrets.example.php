<?php

/**
 * Copy to contact.config.secrets.php on the server (not committed to git).
 * Use AWS SES SMTP credentials from IAM → SMTP settings.
 */
return [
    'smtp_username' => 'AKIAXXXXXXXXXXXXXXXX',
    'smtp_password' => 'your-ses-smtp-password',
];
