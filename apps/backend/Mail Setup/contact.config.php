<?php

$config = [
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
        'username' => '',
        'password' => '',
    ],
];

$secretsPath = __DIR__ . '/contact.config.secrets.php';
if (is_file($secretsPath)) {
    $secrets = require $secretsPath;
    $config['ses']['username'] = (string) ($secrets['smtp_username'] ?? '');
    $config['ses']['password'] = (string) ($secrets['smtp_password'] ?? '');
}

return $config;
