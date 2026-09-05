$token = "8134671011:AAGi4n7E9mvcPwEGAUdpIyZ1z9HVjwpIX-M"
$offset = 0
Write-Host "Listening for pre_checkout_query..."
while ($true) {
    try {
        $updates = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates?offset=$offset&timeout=10"
        if ($updates.ok -and $updates.result.Count -gt 0) {
            foreach ($update in $updates.result) {
                $offset = $update.update_id + 1
                if ($update.pre_checkout_query) {
                    $pq_id = $update.pre_checkout_query.id
                    $body = @{ pre_checkout_query_id = $pq_id; ok = $true } | ConvertTo-Json
                    Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/answerPreCheckoutQuery" -Method Post -ContentType "application/json" -Body $body
                    Write-Host "Answered pre_checkout_query: $pq_id"
                }
                if ($update.message.successful_payment) {
                    Write-Host "Successful payment received from: $($update.message.from.id)"
                }
            }
        }
    } catch {
        Write-Host "Error: $_"
    }
}
