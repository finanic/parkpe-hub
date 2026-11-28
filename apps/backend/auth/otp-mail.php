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
$preview = ($message['template_preview'] ?? false) === true;
$role = (string) ($message['role'] ?? 'customer');
if ($to === '' || $subject === '' || (!$preview && $text === '') || !filter_var($to, FILTER_VALIDATE_EMAIL)) {
    exit(1);
}
if (!in_array($role, ['customer', 'retailer'], true)) {
    exit(1);
}

$configPath = getenv('AUTH_MAIL_CONFIG') ?: '';
$smtpPath = getenv('AUTH_SES_SMTP_PHP') ?: '';
$backendRoot = realpath(dirname(__DIR__));
$allowedRoots = array_values(array_filter([
    $backendRoot !== false ? $backendRoot : null,
    $backendRoot !== false ? realpath($backendRoot . '/Mail Setup') : null,
]));
$resolveLocal = static function (string $path) use ($allowedRoots, $backendRoot): string {
    $candidates = [$path];
    if ($backendRoot !== false && $path !== '' && $path[0] !== '/' && $path[0] !== '\\') {
        $candidates[] = $backendRoot . DIRECTORY_SEPARATOR . $path;
    }
    foreach ($candidates as $candidate) {
        $real = realpath($candidate);
        if ($real === false || !is_file($real)) {
            continue;
        }
        foreach ($allowedRoots as $root) {
            if ($root !== false && str_starts_with($real, rtrim((string) $root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR)) {
                return $real;
            }
        }
    }
    return '';
};
$configPath = $resolveLocal($configPath);
$smtpPath = $resolveLocal($smtpPath);
if ($configPath === '' || $smtpPath === '') {
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
$isPayswap = $role === 'retailer';
$brand = $isPayswap ? 'PaySwap' : 'ParkPe';
$name = $brand;
$repoRoot = realpath(dirname(__DIR__, 2));
$logoCandidate = ($repoRoot !== false ? $repoRoot : dirname(__DIR__, 2)) . ($isPayswap
    ? '/payswap/assets/payswap-logo.png'
    : '/parkpe/assets/img/logo/parkpe_logo.png');
$logoReal = realpath($logoCandidate);
$logo = (
    $repoRoot !== false
    && $logoReal !== false
    && str_starts_with($logoReal, $repoRoot . DIRECTORY_SEPARATOR)
    && is_file($logoReal)
) ? 'data:image/png;base64,' . base64_encode((string) file_get_contents($logoReal)) : '';
$safeSubject = htmlspecialchars($subject, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$safeBrand = htmlspecialchars($brand, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$otp = '';
if (!$preview && preg_match('/\b([0-9]{6})\b/', $text, $match) === 1) {
    $otp = $match[1];
}
$content = $preview
    ? '<p style="margin:0;color:#475569;font-size:16px;line-height:1.7">This ' . $safeBrand . ' email design preview contains no sign-in code.</p>'
    : ($otp !== ''
        ? '<p style="margin:0 0 20px;color:#475569;font-size:16px;line-height:1.7">Use this one-time code to continue:</p><div style="margin:0 auto 20px;padding:18px 24px;border:1px solid #dbece2;border-radius:14px;background:#f3faf5;color:#123b2b;font-size:34px;font-weight:700;letter-spacing:10px;text-align:center">' . htmlspecialchars($otp, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . '</div><p style="margin:0;color:#64748b;font-size:14px;line-height:1.7">This code expires in 10 minutes. For your security, do not share it with anyone.</p>'
        : '<p style="margin:0;color:#475569;font-size:16px;line-height:1.7">' . nl2br(htmlspecialchars($text, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')) . '</p>');
$brandMark = $logo !== ''
    ? '<img src="' . $logo . '" width="150" alt="' . $safeBrand . '" style="display:block;width:auto;max-width:170px;height:auto;max-height:72px;margin:0 auto">'
    : '<span style="color:#17623d;font-size:22px;font-weight:700">' . $safeBrand . '</span>';
$html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>' . $safeSubject . '</title></head><body style="margin:0;padding:32px 12px;background:#f1f5f2;font-family:Arial,Helvetica,sans-serif;color:#173326"><div style="display:none;max-height:0;overflow:hidden;opacity:0">' . ($preview ? 'A preview of the ' . $safeBrand . ' verification email.' : 'Your ' . $safeBrand . ' verification code is inside.') . '</div><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;margin:0 auto"><tr><td style="padding:0 0 22px;text-align:center">' . $brandMark . '</td></tr><tr><td style="padding:34px 32px 30px;border:1px solid #e1e9e3;border-radius:20px;background:#ffffff;box-shadow:0 12px 36px rgba(21,61,41,.08)"><p style="margin:0 0 10px;color:#21804d;font-size:12px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase">Account security</p><h1 style="margin:0 0 18px;color:#123b2b;font-size:26px;line-height:1.25">' . ($preview ? 'A clearer, safer email' : 'Verify your email') . '</h1>' . $content . '<div style="height:1px;margin:26px 0 18px;background:#e8eee9"></div><p style="margin:0;color:#718078;font-size:13px;line-height:1.6">If you did not request this, you can safely ignore this email. We will never ask you to share your code.</p></td></tr><tr><td style="padding:18px 20px;text-align:center;color:#7b8981;font-size:12px;line-height:1.6">Payswap Fintech Private Limited<br>Automated message — please do not reply.</td></tr></table></body></html>';
$plainText = $preview
    ? $brand . ' email design preview. This test message contains no sign-in code.'
    : $text;
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
    $plainText,
    $html
);

exit($sent ? 0 : 1);
