# src/rlcoach/api/routers/billing.py
"""Stripe billing endpoints for subscription management."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ...db.models import User
from ...db.session import get_session
from ..auth import AuthenticatedUser

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # Pro tier $10/mo

# App URLs
APP_URL = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutResponse(BaseModel):
    """Response containing checkout session URL."""
    checkout_url: str


class PortalResponse(BaseModel):
    """Response containing billing portal URL."""
    portal_url: str


class SubscriptionStatus(BaseModel):
    """Current subscription status."""
    tier: str
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    current_user: AuthenticatedUser,
) -> CheckoutResponse:
    """Create a Stripe Checkout session for Pro subscription."""
    if not STRIPE_PRICE_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe not configured"
        )

    with get_session() as session:
        user = session.query(User).filter(User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already Pro
        if user.subscription_tier == "pro":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already subscribed to Pro"
            )

        try:
            # Create or get Stripe customer
            if not user.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    metadata={"user_id": str(user.id)}
                )
                user.stripe_customer_id = customer.id
                session.commit()

            # Create checkout session
            checkout_session = stripe.checkout.Session.create(
                customer=user.stripe_customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price": STRIPE_PRICE_ID,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=f"{APP_URL}/settings?session_id={{CHECKOUT_SESSION_ID}}&success=true",
                cancel_url=f"{APP_URL}/upgrade?canceled=true",
                metadata={
                    "user_id": str(user.id),
                },
                subscription_data={
                    "metadata": {
                        "user_id": str(user.id),
                    },
                },
            )

            return CheckoutResponse(checkout_url=checkout_session.url)

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payment service error"
            )


@router.post("/portal", response_model=PortalResponse)
async def create_portal_session(
    current_user: AuthenticatedUser,
) -> PortalResponse:
    """Create a Stripe Customer Portal session for subscription management."""
    with get_session() as session:
        user = session.query(User).filter(User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.stripe_customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No subscription to manage"
            )

        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=user.stripe_customer_id,
                return_url=f"{APP_URL}/settings",
            )

            return PortalResponse(portal_url=portal_session.url)

        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating portal: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Payment service error"
            )


@router.get("/status", response_model=SubscriptionStatus)
async def get_subscription_status(
    current_user: AuthenticatedUser,
) -> SubscriptionStatus:
    """Get current subscription status."""
    with get_session() as session:
        user = session.query(User).filter(User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        result = SubscriptionStatus(
            tier=user.subscription_tier or "free",
            status=user.subscription_status,
        )

        # Fetch current period info from Stripe if subscribed
        if user.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
                result.current_period_end = datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                )
                result.cancel_at_period_end = subscription.cancel_at_period_end
            except stripe.error.StripeError:
                # Return basic info if Stripe fails
                pass

        return result


# Webhook endpoint - separate path for clarity
webhook_router = APIRouter(tags=["stripe-webhook"])


@webhook_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("Invalid webhook payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Process the event
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Processing Stripe event: {event_type}")

    with get_session() as session:
        if event_type == "checkout.session.completed":
            await handle_checkout_completed(session, data)
        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(session, data)
        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(session, data)
        elif event_type == "invoice.payment_failed":
            await handle_payment_failed(session, data)
        else:
            logger.info(f"Unhandled event type: {event_type}")

    return {"received": True}


async def handle_checkout_completed(session, checkout_session):
    """Handle successful checkout - activate Pro subscription."""
    user_id = checkout_session.get("metadata", {}).get("user_id")
    subscription_id = checkout_session.get("subscription")
    customer_id = checkout_session.get("customer")

    if not user_id:
        logger.error("No user_id in checkout metadata")
        return

    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"User {user_id} not found for checkout")
        return

    user.subscription_tier = "pro"
    user.subscription_status = "active"
    user.stripe_subscription_id = subscription_id
    user.stripe_customer_id = customer_id

    # Reset token budget on new subscription
    user.token_budget_used = 0
    user.token_budget_reset_at = datetime.now(timezone.utc)

    session.commit()
    logger.info(f"User {user_id} upgraded to Pro")


async def handle_subscription_updated(session, subscription):
    """Handle subscription status changes."""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        # Try to find by customer ID
        customer_id = subscription.get("customer")
        user = session.query(User).filter(User.stripe_customer_id == customer_id).first()
    else:
        user = session.query(User).filter(User.id == user_id).first()

    if not user:
        logger.warning("User not found for subscription update")
        return

    status = subscription.get("status")

    if status == "active":
        user.subscription_tier = "pro"
        user.subscription_status = "active"
    elif status == "past_due":
        user.subscription_status = "past_due"
    elif status == "canceled":
        user.subscription_tier = "free"
        user.subscription_status = "canceled"
    elif status == "unpaid":
        user.subscription_tier = "free"
        user.subscription_status = "unpaid"

    user.stripe_subscription_id = subscription.get("id")
    session.commit()
    logger.info(f"User {user.id} subscription updated: {status}")


async def handle_subscription_deleted(session, subscription):
    """Handle subscription cancellation."""
    customer_id = subscription.get("customer")

    user = session.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        logger.warning("User not found for subscription deletion")
        return

    user.subscription_tier = "free"
    user.subscription_status = "canceled"
    user.stripe_subscription_id = None

    session.commit()
    logger.info(f"User {user.id} subscription canceled")


async def handle_payment_failed(session, invoice):
    """Handle failed payment."""
    customer_id = invoice.get("customer")

    user = session.query(User).filter(User.stripe_customer_id == customer_id).first()
    if not user:
        logger.warning("User not found for payment failure")
        return

    user.subscription_status = "past_due"
    session.commit()
    logger.info(f"User {user.id} payment failed, marked past_due")
