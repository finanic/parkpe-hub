<?php

declare(strict_types=1);

/**
 * Sends one verification email through parkpe-landing public/api/ses-smtp.php.
 * SMTP settings stay in AUTH_MAIL_CONFIG (the existing contact.config.php).
 * This file does not contain credentials.
 */

$raw = stream_get_contents(STDIN);
$message = json_decode($raw === false ? '' : $raw, true);
if (!is_array($message)) {
    exit(1);
}

$to = trim((string) ($message['to'] ?? ''));
$subject = trim((string) ($message['subject'] ?? ''));
$text = (string) ($message['text'] ?? '');
if ($to === '' || $subject === '' || $text === '' || !filter_var($to, FILTER_VALIDATE_EMAIL)) {
    exit(1);
}

$configPath = getenv('AUTH_MAIL_CONFIG') ?: '';
$smtpPath = getenv('AUTH_SES_SMTP_PHP') ?: '';
if ($configPath === '' || $smtpPath === '' || !is_file($configPath) || !is_file($smtpPath)) {
    exit(2);
}

$config = require $configPath;
$ses = is_array($config['ses'] ?? null) ? $config['ses'] : [];
$host = (string) ($ses['host'] ?? '');
$username = (string) ($ses['username'] ?? '');
$password = (string) ($ses['password'] ?? '');
if ($host === '' || $username === '' || $password === '') {
    exit(2);
}

require_once $smtpPath;

$from = (string) ($config['from_email'] ?? 'noreply@parkpe.in');
$name = (string) ($config['site_name'] ?? 'ParkPe');
$html = '<p>' . htmlspecialchars($text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . '</p>';
$sent = sesSmtpSendMessage(
    [
        'host' => $host,
        'port' => (int) ($ses['port'] ?? 587),
        'username' => $username,
        'password' => $password,
    ],
    $from,
    $name,
    [$to],
    $subject,
    $text,
    $html
);

exit($sent ? 0 : 1);
