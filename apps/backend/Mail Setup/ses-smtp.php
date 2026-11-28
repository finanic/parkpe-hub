<?php

declare(strict_types=1);

/**
 * AWS SES SMTP sender with HTML + multiple recipients.
 *
 * @param array{
 *   host: string,
 *   port: int,
 *   username: string,
 *   password: string,
 * } $smtp
 * @param list<string> $toEmails
 * @param list<string> $ccEmails
 */
function sesSmtpSendMessage(
    array $smtp,
    string $fromEmail,
    string $fromName,
    array $toEmails,
    string $subject,
    string $textBody,
    string $htmlBody,
    string $replyTo = '',
    array $ccEmails = []
): bool {
    $toEmails = array_values(array_filter(array_map('trim', $toEmails)));
    $ccEmails = array_values(array_filter(array_map('trim', $ccEmails)));

    if ($toEmails === []) {
        return false;
    }

    $host = $smtp['host'];
    $port = (int) $smtp['port'];
    $username = $smtp['username'];
    $password = $smtp['password'];

    $socket = @stream_socket_client(
        sprintf('tcp://%s:%d', $host, $port),
        $errno,
        $errstr,
        15,
        STREAM_CLIENT_CONNECT
    );

    if ($socket === false) {
        return false;
    }

    stream_set_timeout($socket, 30);

    if (!smtpExpect($socket, [220])) {
        fclose($socket);
        return false;
    }

    $clientHost = gethostname() ?: 'localhost';
    if (!smtpCommand($socket, 'EHLO ' . $clientHost, [250])
        || !smtpCommand($socket, 'STARTTLS', [220])) {
        fclose($socket);
        return false;
    }

    $crypto = stream_socket_enable_crypto($socket, true, STREAM_CRYPTO_METHOD_TLS_CLIENT);
    if ($crypto !== true) {
        fclose($socket);
        return false;
    }

    if (!smtpCommand($socket, 'EHLO ' . $clientHost, [250])
        || !smtpCommand($socket, 'AUTH LOGIN', [334])
        || !smtpCommand($socket, base64_encode($username), [334])
        || !smtpCommand($socket, base64_encode($password), [235])
        || !smtpCommand($socket, 'MAIL FROM:<' . $fromEmail . '>', [250])) {
        fclose($socket);
        return false;
    }

    foreach (array_merge($toEmails, $ccEmails) as $recipient) {
        if (!smtpCommand($socket, 'RCPT TO:<' . $recipient . '>', [250, 251])) {
            fclose($socket);
            return false;
        }
    }

    if (!smtpCommand($socket, 'DATA', [354])) {
        fclose($socket);
        return false;
    }

    $message = smtpBuildMimeMessage(
        $fromEmail,
        $fromName,
        $toEmails,
        $subject,
        $textBody,
        $htmlBody,
        $replyTo,
        $ccEmails
    );

    if (!smtpSendData($socket, $message) || !smtpExpect($socket, [250])) {
        fclose($socket);
        return false;
    }

    smtpCommand($socket, 'QUIT', [221]);
    fclose($socket);

    return true;
}

/**
 * @param list<string> $toEmails
 * @param list<string> $ccEmails
 */
function smtpBuildMimeMessage(
    string $fromEmail,
    string $fromName,
    array $toEmails,
    string $subject,
    string $textBody,
    string $htmlBody,
    string $replyTo = '',
    array $ccEmails = []
): string {
    $boundary = 'parkpe_' . bin2hex(random_bytes(12));
    $encodedSubject = '=?UTF-8?B?' . base64_encode($subject) . '?=';

    $headers = [
        'Date: ' . gmdate('D, d M Y H:i:s') . ' +0000',
        'From: ' . smtpEncodeAddress($fromName, $fromEmail),
        'To: ' . implode(', ', array_map(static fn (string $email): string => '<' . $email . '>', $toEmails)),
        'Subject: ' . $encodedSubject,
        'MIME-Version: 1.0',
        'X-Mailer: ParkPe Contact',
    ];

    if ($ccEmails !== []) {
        $headers[] = 'Cc: ' . implode(', ', array_map(static fn (string $email): string => '<' . $email . '>', $ccEmails));
    }

    if ($replyTo !== '') {
        $headers[] = 'Reply-To: <' . $replyTo . '>';
    }

    $headers[] = 'Content-Type: multipart/alternative; boundary="' . $boundary . '"';

    $plainPart = smtpNormalizeLines($textBody);
    $htmlPart = smtpNormalizeLines($htmlBody);
    $htmlBase64 = rtrim(chunk_split(base64_encode($htmlPart), 76, "\r\n"));

    $body = implode("\r\n", [
        '--' . $boundary,
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
        '',
        $plainPart,
        '--' . $boundary,
        'Content-Type: text/html; charset=UTF-8',
        'Content-Transfer-Encoding: base64',
        '',
        $htmlBase64,
        '--' . $boundary . '--',
        '',
    ]);

    return smtpNormalizeLines(implode("\r\n", $headers) . "\r\n\r\n" . $body);
}

function smtpNormalizeLines(string $value): string
{
    $value = str_replace(["\r\n", "\r"], "\n", $value);
    return str_replace("\n", "\r\n", $value);
}

function smtpSendData($socket, string $message): bool
{
    $lines = explode("\n", str_replace(["\r\n", "\r"], "\n", $message));

    foreach ($lines as $line) {
        $line = rtrim($line, "\r");
        if ($line !== '' && $line[0] === '.') {
            $line = '.' . $line;
        }

        if (!smtpWrite($socket, $line . "\r\n")) {
            return false;
        }
    }

    return smtpWrite($socket, ".\r\n");
}

/** @deprecated Use sesSmtpSendMessage() */
function sesSmtpSend(
    array $smtp,
    string $fromEmail,
    string $fromName,
    string $toEmail,
    string $subject,
    string $body,
    string $replyTo
): bool {
    return sesSmtpSendMessage(
        $smtp,
        $fromEmail,
        $fromName,
        [$toEmail],
        $subject,
        $body,
        nl2br(htmlspecialchars($body, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')),
        $replyTo
    );
}

function smtpEncodeAddress(string $name, string $email): string
{
    $safeName = str_replace(['"', "\r", "\n"], '', $name);
    return sprintf('"%s" <%s>', $safeName, $email);
}

function smtpWrite($socket, string $message): bool
{
    return fwrite($socket, $message) !== false;
}

function smtpCommand($socket, string $command, array $expectedCodes): bool
{
    if (!smtpWrite($socket, $command . "\r\n")) {
        return false;
    }

    return smtpExpect($socket, $expectedCodes);
}

function smtpExpect($socket, array $expectedCodes): bool
{
    $response = '';

    while (($line = fgets($socket, 515)) !== false) {
        $response .= $line;
        if (isset($line[3]) && $line[3] === ' ') {
            break;
        }
    }

    if ($response === '') {
        return false;
    }

    $code = (int) substr($response, 0, 3);

    return in_array($code, $expectedCodes, true);
}
