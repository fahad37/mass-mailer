document.getElementById('send-btn').addEventListener('click', async () => {
    const email = document.getElementById('smtp-email').value;
    const password = document.getElementById('smtp-password').value;
    const contactsRaw = document.getElementById('contacts-input').value;
    const subject = document.getElementById('email-subject').value;
    const body = document.getElementById('email-body').value;
    const statusSection = document.getElementById('status-section');
    const statusLog = document.getElementById('status-log');
    const btn = document.getElementById('send-btn');

    if (!email || !password || !contactsRaw || !subject || !body) {
        alert('Please fill in all fields.');
        return;
    }

    // Parse CSV
    const lines = contactsRaw.trim().split('\n');
    if (lines.length < 2) {
        alert('Contacts must include a header row and at least one data row.');
        return;
    }

    const headers = lines[0].split(',').map(h => h.trim());
    const contacts = [];

    for (let i = 1; i < lines.length; i++) {
        const row = lines[i].split(',');
        if (row.length === headers.length) {
            const contact = {};
            headers.forEach((header, index) => {
                contact[header] = row[index].trim();
            });
            contacts.push(contact);
        }
    }

    if (contacts.length === 0) {
        alert('No valid contacts found.');
        return;
    }

    // Prepare Payload
    const payload = {
        smtp_config: {
            email: email,
            password: password,
            host: 'smtp.gmail.com',
            port: 587
        },
        template: {
            subject: subject,
            body: body
        },
        contacts: contacts
    };

    // UI Updates
    btn.disabled = true;
    btn.textContent = 'Sending...';
    statusSection.style.display = 'block';
    statusLog.innerHTML = '<div>Starting process...</div>';

    try {
        // Health check first with retry logic
        const checkHealth = async (retries = 3, delay = 1000) => {
            for (let i = 0; i < retries; i++) {
                try {
                    const healthCheck = await fetch('/api/health', { signal: AbortSignal.timeout(5000) });
                    if (healthCheck.ok) return true;
                } catch (e) {
                    console.log(`Health check attempt ${i + 1} failed:`, e);
                    if (i === retries - 1) throw e;
                    await new Promise(r => setTimeout(r, delay));
                }
            }
            return false;
        };

        try {
            await checkHealth();
        } catch (e) {
            throw new Error(`Cannot connect to server. Is it running? Details: ${e.message}`);
        }

        const response = await fetch('/api/send', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        // Try to parse JSON response regardless of status
        let result;
        const text = await response.text();
        try {
            result = JSON.parse(text);
        } catch (e) {
            result = { message: text };
        }

        if (response.ok) {
            statusLog.innerHTML += `<div class="success">${result.message}</div>`;
            
            if (result.results && result.results.length > 0) {
                statusLog.innerHTML += '<h4>Details:</h4><ul>';
                result.results.forEach(res => {
                    const statusClass = res.status === 'sent' ? 'success' : 'error';
                    const msg = res.status === 'sent' ? 'Sent' : `Failed: ${res.error}`;
                    statusLog.innerHTML += `<li class="${statusClass}">${res.email}: ${msg}</li>`;
                });
                statusLog.innerHTML += '</ul>';
            }
        } else {
            statusLog.innerHTML += `<div class="error">Error: ${result.message || response.statusText}</div>`;
        }
    } catch (error) {
        statusLog.innerHTML += `<div class="error">Network/System Error: ${error.message}</div>`;
        statusLog.innerHTML += `<div>Tip: Check if the python server terminal is open and running.</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Send Emails';
    }
});
