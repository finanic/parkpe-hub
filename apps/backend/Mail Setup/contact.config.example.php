<?php

return [
    'to_emails' => [
        'support@parkpe.in',
        'sandeep@payswap.in',
    ],
    'from_email' => 'noreply@parkpe.in',
    'site_name' => 'ParkPe',
    'site_url' => 'https://parkpe.in',
    'logo_url' => 'https://parkpe.in/img/logo/parkpe_logo_email.png',
    'mail_transport' => 'ses_smtp',
    'ses' => [
        'region' => 'ap-south-1',
        'host' => 'email-smtp.ap-south-1.amazonaws.com',
        'port' => 587,
        'username' => 'AKIAXXXXXXXXXXXXXXXX',
        'password' => 'your-ses-smtp-password',
    ],
];
