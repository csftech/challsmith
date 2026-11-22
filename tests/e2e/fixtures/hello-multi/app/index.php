<?php
// The db container may still be starting: retry for up to ~30s.
$pdo = null;
for ($i = 0; $i < 30 && $pdo === null; $i++) {
    try {
        $pdo = new PDO('mysql:host=db;dbname=app', 'root', getenv('DB_PASSWORD'),
            [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    } catch (PDOException $e) {
        sleep(1);
    }
}
if ($pdo === null) {
    http_response_code(503);
    exit("database not ready\n");
}
$pdo->exec('CREATE TABLE IF NOT EXISTS flags (v VARCHAR(255) NOT NULL)');
$pdo->exec('DELETE FROM flags');
$pdo->prepare('INSERT INTO flags (v) VALUES (?)')->execute([getenv('FLAG')]);
echo $pdo->query('SELECT v FROM flags')->fetchColumn(), "\n";
