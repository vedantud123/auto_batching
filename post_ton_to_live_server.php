<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$mac_address = trim(shell_exec("cat /sys/class/net/wlan0/address"));
$mac_address_formatted = str_replace(":", "-", $mac_address);

$sql = "SELECT id, shead_name, ton, client_id, date, status 
        FROM batching_running_logs 
        WHERE status = 'running'";

$result = $conn->query($sql);

$dataToSend = [];
if ($result && $result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $dataToSend[] = [
            'mac_address' => $mac_address_formatted,
            'id'          => $row['id'],
            'shead_name'  => $row['shead_name'],
            'ton'         => $row['ton'],
            'client_id'   => $row['client_id'],
            'date'        => $row['date'],
            'status'      => $row['status']
        ];
    }
}

$conn->close();

$apiUrl = "http://sunfra.com/farm/csv/feed_formula_json.php";

$options = [
    'http' => [
        'header'  => "Content-type: application/json\r\n",
        'method'  => 'POST',
        'content' => json_encode($dataToSend),
        'timeout' => 10
    ]
];
$context  = stream_context_create($options);
$response = file_get_contents($apiUrl, false, $context);

if ($response === FALSE) {
    echo "Error sending data to API";
} else {
    echo "Data sent successfully! Response: " . $response;
}
?>
