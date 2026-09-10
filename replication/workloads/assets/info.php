<?php
header('Content-Type: application/json');
echo json_encode([
    'service'  => 'greenlab-fixed',
    'category' => 'general-purpose',
    'subject'  => 'php-apache',
    'payload'  => str_repeat('phpfixed', 1024),
]);
