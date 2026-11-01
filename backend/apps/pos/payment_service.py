import os
import urllib.parse
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class PaymentGatewayProvider:
    """
    Modular Payment Provider Interface supporting:
    - Standard NPCI Dynamic UPI QR generation (India)
    - Gateway hooks for Razorpay / PhonePe / Stripe
    - Clear configuration auditing for live payment enablement
    """

    @classmethod
    def get_configured_gateways(cls):
        """
        Inspects environment variables to report available payment gateway integrations.
        """
        gateways = {
            'UPI_QR': {
                'enabled': True,
                'mode': 'DYNAMIC_QR',
                'description': 'Direct NPCI UPI QR string generation for GPay, PhonePe, Paytm, BHIM in INR.'
            },
            'RAZORPAY': {
                'enabled': bool(os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_KEY_SECRET')),
                'key_id': os.getenv('RAZORPAY_KEY_ID') or None,
                'missing_config': [] if (os.getenv('RAZORPAY_KEY_ID') and os.getenv('RAZORPAY_KEY_SECRET')) else ['RAZORPAY_KEY_ID', 'RAZORPAY_KEY_SECRET']
            },
            'PHONEPE': {
                'enabled': bool(os.getenv('PHONEPE_MERCHANT_ID') and os.getenv('PHONEPE_SALT_KEY')),
                'merchant_id': os.getenv('PHONEPE_MERCHANT_ID') or None,
                'missing_config': [] if (os.getenv('PHONEPE_MERCHANT_ID') and os.getenv('PHONEPE_SALT_KEY')) else ['PHONEPE_MERCHANT_ID', 'PHONEPE_SALT_KEY', 'PHONEPE_SALT_INDEX']
            }
        }
        return gateways

    @classmethod
    def generate_upi_payment_qr(cls, salon, amount, invoice_number, vpa=None):
        """
        Generates standard NPCI UPI payment URI.
        Format: upi://pay?pa=<vpa>&pn=<payee>&am=<amount>&cu=INR&tn=<invoice_number>
        """
        formatted_amount = f"{Decimal(str(amount)):.2f}"
        
        # Use salon's designated UPI VPA or fallback to salon contact identifier
        payee_vpa = vpa or os.getenv('DEFAULT_SALON_UPI_VPA') or f"{salon.slug}@upi"
        payee_name = salon.name
        transaction_note = f"Invoice {invoice_number}"

        params = {
            'pa': payee_vpa,
            'pn': payee_name,
            'am': formatted_amount,
            'cu': 'INR',
            'tn': transaction_note,
        }
        query_string = urllib.parse.urlencode(params)
        upi_uri = f"upi://pay?{query_string}"

        # Generate a standard QR image URL using an open encoded helper or direct SVG
        encoded_upi = urllib.parse.quote(upi_uri)
        qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={encoded_upi}"

        return {
            'provider': 'UPI',
            'currency': 'INR',
            'amount': formatted_amount,
            'payee_vpa': payee_vpa,
            'payee_name': payee_name,
            'invoice_number': invoice_number,
            'upi_uri': upi_uri,
            'qr_image_url': qr_image_url,
            'instructions': 'Scan with Google Pay, PhonePe, Paytm, or BHIM UPI app to settle payment.'
        }

