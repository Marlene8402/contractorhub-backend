import os
import json
import requests
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from intuit_oauth import AuthClient
from .models import Company, QBSyncLog, Project, Invoice

class QBIntegration:
    """Handle QuickBooks OAuth and API operations"""
    
    def __init__(self, company):
        self.company = company
        self.client_id = settings.QB_CLIENT_ID
        self.client_secret = settings.QB_CLIENT_SECRET
        self.redirect_uri = settings.QB_REDIRECT_URI
        self.realm_id = company.qb_realm_id or settings.QB_REALM_ID
        self.access_token = company.qb_access_token
        self.refresh_token = company.qb_refresh_token
        
        self.auth_client = AuthClient(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment='sandbox'
        )
        
        self.qb_api_base = 'https://quickbooks.api.intuit.com/v2/company'
    
    def get_auth_url(self):
        """Generate QB authorization URL for OAuth flow"""
        return self.auth_client.get_authorization_url(
            realm_id='',
            state=''
        )
    
    def get_access_token(self, auth_code):
        """Exchange authorization code for access and refresh tokens"""
        try:
            auth_response = self.auth_client.get_token(auth_code)
            
            self.company.qb_access_token = auth_response['access_token']
            self.company.qb_refresh_token = auth_response['refresh_token']
            self.company.qb_realm_id = auth_response['x_refresh_token_expires_in']
            self.company.qb_token_expires_at = timezone.now() + timedelta(
                seconds=int(auth_response['expires_in'])
            )
            self.company.qb_connected = True
            self.company.save()
            
            return True
        except Exception as e:
            print(f"QB Auth Error: {str(e)}")
            return False
    
    def refresh_access_token(self):
        """Refresh expired access token"""
        try:
            auth_response = self.auth_client.refresh(self.refresh_token)
            
            self.company.qb_access_token = auth_response['access_token']
            self.company.qb_refresh_token = auth_response['refresh_token']
            self.company.qb_token_expires_at = timezone.now() + timedelta(
                seconds=int(auth_response['expires_in'])
            )
            self.company.save()
            
            return True
        except Exception as e:
            print(f"Token Refresh Error: {str(e)}")
            self.company.qb_connected = False
            self.company.save()
            return False
    
    def is_token_expired(self):
        """Check if current access token is expired"""
        if not self.company.qb_token_expires_at:
            return True
        return timezone.now() >= self.company.qb_token_expires_at
    
    def ensure_valid_token(self):
        """Ensure we have a valid access token, refresh if needed"""
        if self.is_token_expired():
            return self.refresh_access_token()
        return True
    
    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to QB API"""
        if not self.ensure_valid_token():
            raise Exception("Unable to obtain valid QB token")
        
        headers = {
            'Authorization': f'Bearer {self.company.qb_access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f'{self.qb_api_base}/{self.realm_id}{endpoint}'
        
        try:
            if method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"QB API Error: {str(e)}")
    
    def create_customer(self, project):
        """Create QB customer from project"""
        try:
            data = {
                "DisplayName": project.client_name[:20],
                "PrimaryEmailAddr": {
                    "Address": self.company.email
                },
                "PrimaryPhone": {
                    "FreeFormNumber": self.company.phone or ""
                }
            }
            
            response = self._make_request('POST', '/query?query=select * from Customer where DisplayName like ', data)
            
            # Log sync
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='customer',
                status='success',
                direction='push',
                qb_id=response.get('id'),
                response_data=response
            )
            
            return response.get('id')
        except Exception as e:
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='customer',
                status='failed',
                direction='push',
                error_message=str(e)
            )
            return None
    
    def create_invoice(self, invoice):
        """Push invoice to QB"""
        try:
            # Get or create QB customer
            if not invoice.project.qb_customer_id:
                invoice.project.qb_customer_id = self.create_customer(invoice.project)
                invoice.project.save()
            
            data = {
                "Line": [
                    {
                        "Amount": float(invoice.amount),
                        "DetailType": "SalesItemLineDetail",
                        "Description": invoice.description or invoice.project.name,
                        "SalesItemLineDetail": {
                            "ItemRef": {
                                "value": "1",
                                "name": "Services"
                            }
                        }
                    }
                ],
                "CustomerRef": {
                    "value": invoice.project.qb_customer_id
                },
                "DueDate": invoice.due_date.isoformat(),
                "DocNumber": invoice.invoice_number
            }
            
            response = self._make_request('POST', '/invoice', data)
            
            invoice.qb_invoice_id = response.get('Id')
            invoice.qb_synced = True
            invoice.save()
            
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='invoice',
                status='success',
                direction='push',
                qb_id=response.get('Id'),
                response_data=response
            )
            
            return True
        except Exception as e:
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='invoice',
                status='failed',
                direction='push',
                error_message=str(e)
            )
            return False
    
    def sync_invoices_from_qb(self):
        """Pull invoices from QB"""
        try:
            query = "select * from Invoice"
            response = self._make_request('GET', f'/query?query={query}')
            
            invoices = response.get('QueryResponse', {}).get('Invoice', [])
            
            for qb_invoice in invoices:
                # Match with local invoice by number
                try:
                    invoice = Invoice.objects.get(invoice_number=qb_invoice['DocNumber'])
                    invoice.qb_invoice_id = qb_invoice['Id']
                    invoice.qb_synced = True
                    invoice.save()
                except Invoice.DoesNotExist:
                    pass
            
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='invoice',
                status='success',
                direction='pull',
                response_data={'invoice_count': len(invoices)}
            )
            
            return len(invoices)
        except Exception as e:
            QBSyncLog.objects.create(
                company=self.company,
                sync_type='invoice',
                status='failed',
                direction='pull',
                error_message=str(e)
            )
            return 0
