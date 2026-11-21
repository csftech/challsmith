<?php
if (isset($_GET['give'])) {
    echo getenv('FLAG'), "\n";
} else {
    echo "Hello! Try ?give=1\n";
}
